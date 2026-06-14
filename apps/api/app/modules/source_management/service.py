from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel

from app.modules.auth_policy.schemas import RequestContext
from app.modules.source_management.models import IngestionJob, KnowledgeChunk, KnowledgeSource, SourceDocument
from app.modules.telemetry.service import write_audit_event


class SourceCreate(BaseModel):
    type: str = "inline"
    name: str
    connection_ref: str = ""
    sync_policy: str = "manual"
    permission_mode: str = "tenant"


class SourcePatch(BaseModel):
    type: str | None = None
    name: str | None = None
    status: str | None = None
    sync_policy: str | None = None
    permission_mode: str | None = None
    connection_ref: str | None = None


class SyncRequest(BaseModel):
    sync_reason: str = "manual_resync"


_sources: dict[str, KnowledgeSource] = {}
_documents: dict[str, SourceDocument] = {}
_chunks: dict[str, KnowledgeChunk] = {}
_jobs: dict[str, IngestionJob] = {}


def reset_source_store() -> None:
    _sources.clear()
    _documents.clear()
    _chunks.clear()
    _jobs.clear()


def _tenant_sources(context: RequestContext) -> list[KnowledgeSource]:
    return [source for source in _sources.values() if source.tenant_id == context.tenant_id]


def list_sources(context: RequestContext) -> list[KnowledgeSource]:
    return _tenant_sources(context)


def create_source(context: RequestContext, payload: SourceCreate) -> KnowledgeSource:
    source = KnowledgeSource(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        type=payload.type,
        name=payload.name,
        connection_ref=payload.connection_ref,
        sync_policy=payload.sync_policy,
        permission_mode=payload.permission_mode,
    )
    _sources[source.id] = source
    write_audit_event(context, "source.create", "knowledge_source", source.id)
    return source


def get_source(context: RequestContext, source_id: str) -> KnowledgeSource:
    source = _sources.get(source_id)
    if source is None or source.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


def update_source(context: RequestContext, source_id: str, payload: SourcePatch) -> KnowledgeSource:
    source = get_source(context, source_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    write_audit_event(context, "source.update", "knowledge_source", source.id)
    return source


def delete_source(context: RequestContext, source_id: str, delete_mode: str = "disable") -> IngestionJob:
    source = get_source(context, source_id)
    source.status = "disabled"
    job = _enqueue_job(context, source_id, "cleanup_source", delete_mode)
    write_audit_event(context, "source.delete", "knowledge_source", source.id)
    return job


def _enqueue_job(context: RequestContext, source_id: str, job_type: str, reason: str | None) -> IngestionJob:
    job = IngestionJob(id=str(uuid4()), tenant_id=context.tenant_id, source_id=source_id, job_type=job_type, reason=reason)
    _jobs[job.id] = job
    return job


def trigger_sync(context: RequestContext, source_id: str, payload: SyncRequest) -> IngestionJob:
    source = get_source(context, source_id)
    job_type = payload.sync_reason if payload.sync_reason in {
        "initial_sync", "scheduled_refresh", "incremental_update", "manual_resync", "retry_failed_sync", "permission_refresh", "cleanup_source"
    } else "manual_resync"
    job = _enqueue_job(context, source_id, job_type, payload.sync_reason)
    run_sync_job(context, job.id)
    write_audit_event(context, "source.sync", "ingestion_job", job.id)
    source.last_sync_at = datetime.now(timezone.utc)
    return job


def run_sync_job(context: RequestContext, job_id: str) -> IngestionJob:
    job = _jobs[job_id]
    source = get_source(context, job.source_id)
    try:
        if job.job_type == "cleanup_source":
            for chunk_id in [cid for cid, chunk in _chunks.items() if chunk.source_id == source.id]:
                _chunks.pop(chunk_id, None)
            job.status = "completed"
            source.last_sync_status = "cleanup_complete"
            return job
        docs = _load_documents_from_source(source)
        if not docs:
            raise ValueError("No documents found for source")
        _replace_source_documents(context, source, docs)
        job.status = "completed"
        source.last_sync_status = "success"
        source.last_failure_reason = None
        source.last_sync_at = datetime.now(timezone.utc)
    except Exception as exc:  # keep last-known-good chunks on sync failure
        job.status = "failed"
        source.last_sync_status = "failed"
        source.last_failure_reason = str(exc)
    return job


def _load_documents_from_source(source: KnowledgeSource) -> list[tuple[str, str, str]]:
    if source.type == "inline":
        text = source.connection_ref.strip() or "SupportLens AI requires citations for every substantive support answer."
        return [("inline-doc", source.name, text)]
    if source.type in {"filesystem", "markdown"}:
        path = Path(source.connection_ref)
        if not path.exists():
            raise FileNotFoundError(f"Source path does not exist: {path}")
        files = sorted([p for p in path.rglob("*.md") if p.is_file()]) if path.is_dir() else [path]
        return [(str(p), p.stem.replace("-", " ").title(), p.read_text(encoding="utf-8")) for p in files]
    raise ValueError(f"Unsupported source type: {source.type}")


def _replace_source_documents(context: RequestContext, source: KnowledgeSource, docs: list[tuple[str, str, str]]) -> None:
    for doc_id in [did for did, doc in _documents.items() if doc.source_id == source.id]:
        _documents.pop(doc_id, None)
    for chunk_id in [cid for cid, chunk in _chunks.items() if chunk.source_id == source.id]:
        _chunks.pop(chunk_id, None)
    for external_id, title, text in docs:
        document = SourceDocument(
            id=str(uuid4()), tenant_id=context.tenant_id, source_id=source.id,
            external_id=external_id, title=title, url=external_id, version=str(hash(text)), text=text,
            acl_metadata={"permission_mode": source.permission_mode},
        )
        _documents[document.id] = document
        for idx, chunk_text in enumerate(chunk_text_for_index(text)):
            chunk = KnowledgeChunk(
                id=str(uuid4()), tenant_id=context.tenant_id, source_id=source.id, document_id=document.id,
                chunk_index=idx, text=chunk_text, citation_anchor=f"{title}#chunk-{idx + 1}",
                acl_metadata=document.acl_metadata,
            )
            _chunks[chunk.id] = chunk


def chunk_text_for_index(text: str, target_words: int = 180, overlap_words: int = 30) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(target_words - overlap_words, 1)
    for start in range(0, len(words), step):
        part = words[start:start + target_words]
        if part:
            chunks.append(" ".join(part))
        if start + target_words >= len(words):
            break
    return chunks


def get_chunks_for_tenant(context: RequestContext) -> list[KnowledgeChunk]:
    return [chunk for chunk in _chunks.values() if chunk.tenant_id == context.tenant_id]


def get_document(document_id: str) -> SourceDocument | None:
    return _documents.get(document_id)


def source_health(context: RequestContext, source_id: str) -> dict[str, object]:
    source = get_source(context, source_id)
    docs = [doc for doc in _documents.values() if doc.source_id == source_id and doc.tenant_id == context.tenant_id]
    chunks = [chunk for chunk in _chunks.values() if chunk.source_id == source_id and chunk.tenant_id == context.tenant_id]
    return {
        "source_id": source_id,
        "status": source.status,
        "last_sync": source.last_sync_at.isoformat() if source.last_sync_at else None,
        "last_sync_status": source.last_sync_status,
        "failure_reason": source.last_failure_reason,
        "document_count": len(docs),
        "chunk_count": len(chunks),
        "freshness": "stale" if source.last_sync_status == "failed" else "fresh",
    }


def list_jobs(context: RequestContext) -> list[IngestionJob]:
    return [job for job in _jobs.values() if job.tenant_id == context.tenant_id]
