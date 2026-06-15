from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.db.models import IngestionJobRow, KnowledgeChunkRow, KnowledgeSourceRow, SourceDocumentRow
from app.db.session import current_session
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


def _to_source(row: KnowledgeSourceRow) -> KnowledgeSource:
    return KnowledgeSource(
        id=row.id,
        tenant_id=row.tenant_id,
        type=row.type,
        name=row.name,
        connection_ref=row.connection_ref,
        status=row.status,
        sync_policy=row.sync_policy,
        permission_mode=row.permission_mode,
        last_sync_at=row.last_sync_at,
        last_sync_status=row.last_sync_status,
        last_failure_reason=row.last_failure_reason,
    )


def _to_document(row: SourceDocumentRow) -> SourceDocument:
    return SourceDocument(
        id=row.id,
        tenant_id=row.tenant_id,
        source_id=row.source_id,
        external_id=row.external_id,
        title=row.title,
        url=row.url or "",
        version=row.version,
        text=row.text,
        freshness_status=row.freshness_status,
        last_modified=row.last_modified,
        acl_metadata=row.acl_metadata,
    )


def _to_chunk(row: KnowledgeChunkRow) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=row.id,
        tenant_id=row.tenant_id,
        source_id=row.source_id,
        document_id=row.document_id,
        chunk_index=row.chunk_index,
        text=row.text,
        citation_anchor=row.citation_anchor,
        acl_metadata=row.acl_metadata,
        embedding=row.embedding,
    )


def _to_job(row: IngestionJobRow) -> IngestionJob:
    return IngestionJob(
        id=row.id,
        tenant_id=row.tenant_id,
        source_id=row.source_id,
        job_type=row.job_type,
        status=row.status,
        reason=row.reason,
        created_at=row.created_at,
    )


def reset_source_store() -> None:
    session = current_session()
    session.execute(delete(KnowledgeChunkRow))
    session.execute(delete(SourceDocumentRow))
    session.execute(delete(IngestionJobRow))
    session.execute(delete(KnowledgeSourceRow))


def _get_source_row(context: RequestContext, source_id: str) -> KnowledgeSourceRow:
    row = current_session().get(KnowledgeSourceRow, source_id)
    if row is None or row.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return row


def list_sources(context: RequestContext) -> list[KnowledgeSource]:
    rows = current_session().scalars(
        select(KnowledgeSourceRow).where(KnowledgeSourceRow.tenant_id == context.tenant_id).order_by(KnowledgeSourceRow.name)
    )
    return [_to_source(row) for row in rows]


def create_source(context: RequestContext, payload: SourceCreate) -> KnowledgeSource:
    source = KnowledgeSourceRow(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        type=payload.type,
        name=payload.name,
        connection_ref=payload.connection_ref,
        sync_policy=payload.sync_policy,
        permission_mode=payload.permission_mode,
    )
    session = current_session()
    session.add(source)
    session.flush()
    write_audit_event(context, "source.create", "knowledge_source", source.id)
    return _to_source(source)


def get_source(context: RequestContext, source_id: str) -> KnowledgeSource:
    return _to_source(_get_source_row(context, source_id))


def update_source(context: RequestContext, source_id: str, payload: SourcePatch) -> KnowledgeSource:
    source = _get_source_row(context, source_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    current_session().flush()
    write_audit_event(context, "source.update", "knowledge_source", source.id)
    return _to_source(source)


def delete_source(context: RequestContext, source_id: str, delete_mode: str = "disable") -> IngestionJob:
    source = _get_source_row(context, source_id)
    source.status = "disabled"
    job = _enqueue_job(context, source_id, "cleanup_source", delete_mode)
    write_audit_event(context, "source.delete", "knowledge_source", source.id)
    return job


def _enqueue_job(context: RequestContext, source_id: str, job_type: str, reason: str | None) -> IngestionJob:
    job = IngestionJobRow(id=str(uuid4()), tenant_id=context.tenant_id, source_id=source_id, job_type=job_type, reason=reason)
    session = current_session()
    session.add(job)
    session.flush()
    return _to_job(job)


def trigger_sync(context: RequestContext, source_id: str, payload: SyncRequest) -> IngestionJob:
    source = _get_source_row(context, source_id)
    job_type = payload.sync_reason if payload.sync_reason in {
        "initial_sync", "scheduled_refresh", "incremental_update", "manual_resync", "retry_failed_sync", "permission_refresh", "cleanup_source"
    } else "manual_resync"
    job = _enqueue_job(context, source_id, job_type, payload.sync_reason)
    job = run_sync_job(context, job.id)
    write_audit_event(context, "source.sync", "ingestion_job", job.id)
    source.last_sync_at = datetime.now(timezone.utc)
    current_session().flush()
    return job


def run_sync_job(context: RequestContext, job_id: str) -> IngestionJob:
    session = current_session()
    job = session.get(IngestionJobRow, job_id)
    if job is None or job.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found")
    source = _get_source_row(context, job.source_id)
    try:
        if job.job_type == "cleanup_source":
            session.execute(delete(KnowledgeChunkRow).where(KnowledgeChunkRow.source_id == source.id))
            job.status = "completed"
            source.last_sync_status = "cleanup_complete"
            session.flush()
            return _to_job(job)
        docs = _load_documents_from_source(source)
        if not docs:
            raise ValueError("No documents found for source")
        with session.begin_nested():
            _replace_source_documents(context, source, docs)
        job.status = "completed"
        source.last_sync_status = "success"
        source.last_failure_reason = None
        source.last_sync_at = datetime.now(timezone.utc)
    except Exception as exc:  # keep last-known-good chunks on sync failure
        job.status = "failed"
        source.last_sync_status = "failed"
        source.last_failure_reason = str(exc)
    session.flush()
    return _to_job(job)


def _load_documents_from_source(source: KnowledgeSourceRow) -> list[tuple[str, str, str]]:
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


def _replace_source_documents(context: RequestContext, source: KnowledgeSourceRow, docs: list[tuple[str, str, str]]) -> None:
    session = current_session()
    session.execute(delete(KnowledgeChunkRow).where(KnowledgeChunkRow.source_id == source.id))
    session.execute(delete(SourceDocumentRow).where(SourceDocumentRow.source_id == source.id))
    for external_id, title, text in docs:
        document = SourceDocumentRow(
            id=str(uuid4()), tenant_id=context.tenant_id, source_id=source.id,
            external_id=external_id, title=title, url=external_id, version=str(hash(text)), text=text,
            acl_metadata={"permission_mode": source.permission_mode},
        )
        session.add(document)
        session.flush()
        for idx, chunk_text in enumerate(chunk_text_for_index(text)):
            chunk = KnowledgeChunkRow(
                id=str(uuid4()), tenant_id=context.tenant_id, source_id=source.id, document_id=document.id,
                chunk_index=idx, text=chunk_text, citation_anchor=f"{title}#chunk-{idx + 1}",
                acl_metadata=document.acl_metadata,
            )
            session.add(chunk)


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
    rows = current_session().scalars(
        select(KnowledgeChunkRow).where(KnowledgeChunkRow.tenant_id == context.tenant_id).order_by(KnowledgeChunkRow.chunk_index)
    )
    return [_to_chunk(row) for row in rows]


def get_document(document_id: str) -> SourceDocument | None:
    row = current_session().get(SourceDocumentRow, document_id)
    return _to_document(row) if row else None


def source_health(context: RequestContext, source_id: str) -> dict[str, object]:
    source = _get_source_row(context, source_id)
    session = current_session()
    document_count = session.scalar(
        select(func.count()).select_from(SourceDocumentRow).where(SourceDocumentRow.source_id == source_id, SourceDocumentRow.tenant_id == context.tenant_id)
    )
    chunk_count = session.scalar(
        select(func.count()).select_from(KnowledgeChunkRow).where(KnowledgeChunkRow.source_id == source_id, KnowledgeChunkRow.tenant_id == context.tenant_id)
    )
    return {
        "source_id": source_id,
        "status": source.status,
        "last_sync": source.last_sync_at.isoformat() if source.last_sync_at else None,
        "last_sync_status": source.last_sync_status,
        "failure_reason": source.last_failure_reason,
        "document_count": document_count or 0,
        "chunk_count": chunk_count or 0,
        "freshness": "stale" if source.last_sync_status == "failed" else "fresh",
    }


def list_jobs(context: RequestContext) -> list[IngestionJob]:
    rows = current_session().scalars(
        select(IngestionJobRow).where(IngestionJobRow.tenant_id == context.tenant_id).order_by(IngestionJobRow.created_at)
    )
    return [_to_job(job) for job in rows]
