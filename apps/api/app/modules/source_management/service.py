from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text

from app.db.models import IngestionJobRow, KnowledgeChunkRow, KnowledgeSourceRow, SourceDocumentRow
from app.db.session import current_session
from app.modules.auth_policy.schemas import RequestContext
from app.modules.llm_gateway.embeddings import current_embedding_model, current_embedding_version, embed_texts
from app.modules.source_management.connectors import load_documents_from_source
from app.modules.source_management.models import IngestionJob, KnowledgeChunk, KnowledgeSource, SourceDocument
from app.modules.telemetry.service import write_audit_event

logger = logging.getLogger(__name__)

# Job types the sync endpoint and workers accept. Centralized so the API allowlist and
# worker dispatch never drift apart.
VALID_JOB_TYPES = {
    "initial_sync",
    "scheduled_refresh",
    "incremental_update",
    "manual_resync",
    "retry_failed_sync",
    "permission_refresh",
    "cleanup_source",
    "reembed",
}


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
        embedding_model=row.embedding_model,
        embedding_version=row.embedding_version,
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
    job_type = payload.sync_reason if payload.sync_reason in VALID_JOB_TYPES else "manual_resync"
    job = _enqueue_job(context, source_id, job_type, payload.sync_reason)
    # Async dispatch (RQ) is opt-in via settings. When it is enabled the API returns the
    # queued job immediately and a worker runs it; otherwise we run it inline so local
    # development and the synchronous test suite keep working unchanged.
    from app.modules.source_management.queue import enqueue_or_run_inline

    job = enqueue_or_run_inline(context, job.id)
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
    logger.info("Sync job start job_id=%s type=%s source_id=%s", job.id, job.job_type, source.id)
    try:
        if job.job_type == "cleanup_source":
            session.execute(delete(KnowledgeChunkRow).where(KnowledgeChunkRow.source_id == source.id))
            job.status = "completed"
            source.last_sync_status = "cleanup_complete"
            session.flush()
            logger.info("Cleanup complete job_id=%s source_id=%s", job.id, source.id)
            return _to_job(job)
        if job.job_type == "permission_refresh":
            updated = _refresh_permissions(context, source)
            job.status = "completed"
            source.last_sync_status = "success"
            session.flush()
            logger.info("Permission refresh complete job_id=%s source_id=%s chunks=%d", job.id, source.id, updated)
            return _to_job(job)
        if job.job_type == "reembed":
            count = _reembed_source_chunks(context, source)
            job.status = "completed"
            source.last_sync_status = "success"
            session.flush()
            logger.info("Re-embed complete job_id=%s source_id=%s chunks=%d", job.id, source.id, count)
            return _to_job(job)

        docs = load_documents_from_source(source.type, source.name, source.connection_ref)
        if not docs:
            raise ValueError("No documents found for source")
        # The savepoint protects last-known-good chunks if replacement fails midway.
        with session.begin_nested():
            doc_count, chunk_count = _replace_source_documents(context, source, docs)
        job.status = "completed"
        source.last_sync_status = "success"
        source.last_failure_reason = None
        source.last_sync_at = datetime.now(timezone.utc)
        logger.info("Sync complete job_id=%s source_id=%s docs=%d chunks=%d", job.id, source.id, doc_count, chunk_count)
    except Exception as exc:  # keep last-known-good chunks on sync failure
        job.status = "failed"
        source.last_sync_status = "failed"
        source.last_failure_reason = str(exc)
        # Log the failure with a stack trace; the index is left intact by the savepoint above.
        logger.error("Sync job failed job_id=%s source_id=%s", job.id, source.id, exc_info=True)
    session.flush()
    return _to_job(job)


def _replace_source_documents(
    context: RequestContext, source: KnowledgeSourceRow, docs: list[tuple[str, str, str]]
) -> tuple[int, int]:
    session = current_session()
    session.execute(delete(KnowledgeChunkRow).where(KnowledgeChunkRow.source_id == source.id))
    session.execute(delete(SourceDocumentRow).where(SourceDocumentRow.source_id == source.id))
    chunk_count = 0
    for external_id, title, doc_text in docs:
        document = SourceDocumentRow(
            id=str(uuid4()), tenant_id=context.tenant_id, source_id=source.id,
            external_id=external_id, title=title, url=external_id, version=str(hash(doc_text)), text=doc_text,
            acl_metadata={"permission_mode": source.permission_mode},
        )
        session.add(document)
        session.flush()
        chunk_texts = chunk_text_for_index(doc_text)
        # Embed the whole document's chunks in one batch so the embedder loads once per doc.
        embeddings = embed_texts(chunk_texts) if chunk_texts else []
        for idx, (chunk_text, embedding) in enumerate(zip(chunk_texts, embeddings)):
            chunk = KnowledgeChunkRow(
                id=str(uuid4()), tenant_id=context.tenant_id, source_id=source.id, document_id=document.id,
                chunk_index=idx, text=chunk_text, citation_anchor=f"{title}#chunk-{idx + 1}",
                acl_metadata=document.acl_metadata,
                embedding=embedding,
                embedding_model=current_embedding_model(),
                embedding_version=current_embedding_version(),
            )
            session.add(chunk)
            session.flush()
            _write_pg_vector(chunk.id, embedding)
            chunk_count += 1
    return len(docs), chunk_count


def _write_pg_vector(chunk_id: str, embedding: list[float]) -> None:
    """Mirror the JSON embedding into the native pgvector column when on Postgres.

    The ORM model only knows the portable JSON column, so the native vector (used by the
    similarity index) is written with a small raw UPDATE. It is a no-op on SQLite.
    """
    session = current_session()
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
    session.execute(
        text("UPDATE knowledge_chunks SET embedding_vector = CAST(:vec AS vector) WHERE id = :id"),
        {"vec": vector_literal, "id": chunk_id},
    )


def _reembed_source_chunks(context: RequestContext, source: KnowledgeSourceRow) -> int:
    """Re-embed only chunks whose stored model/version differs from the current embedder."""
    session = current_session()
    model, version = current_embedding_model(), current_embedding_version()
    rows = session.scalars(
        select(KnowledgeChunkRow).where(
            KnowledgeChunkRow.source_id == source.id,
            KnowledgeChunkRow.tenant_id == context.tenant_id,
        )
    ).all()
    stale = [row for row in rows if row.embedding_model != model or row.embedding_version != version]
    if not stale:
        return 0
    embeddings = embed_texts([row.text for row in stale])
    for row, embedding in zip(stale, embeddings):
        row.embedding = embedding
        row.embedding_model = model
        row.embedding_version = version
        _write_pg_vector(row.id, embedding)
    session.flush()
    return len(stale)


def _refresh_permissions(context: RequestContext, source: KnowledgeSourceRow) -> int:
    """Re-apply the source permission mode onto its documents and chunks.

    Real connectors will resolve ACLs from the source system here; for the current
    connectors we propagate the source's permission mode so ACL metadata stays consistent.
    """
    session = current_session()
    acl = {"permission_mode": source.permission_mode}
    documents = session.scalars(
        select(SourceDocumentRow).where(SourceDocumentRow.source_id == source.id, SourceDocumentRow.tenant_id == context.tenant_id)
    ).all()
    for document in documents:
        document.acl_metadata = acl
    chunks = session.scalars(
        select(KnowledgeChunkRow).where(KnowledgeChunkRow.source_id == source.id, KnowledgeChunkRow.tenant_id == context.tenant_id)
    ).all()
    for chunk in chunks:
        chunk.acl_metadata = acl
    session.flush()
    return len(chunks)


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


def get_job(context: RequestContext, job_id: str) -> IngestionJob:
    job = current_session().get(IngestionJobRow, job_id)
    if job is None or job.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found")
    return _to_job(job)


def reembed_source(context: RequestContext, source_id: str) -> IngestionJob:
    """Public entrypoint to enqueue/run a re-embedding pass for a source's chunks."""
    _get_source_row(context, source_id)
    job = _enqueue_job(context, source_id, "reembed", "reembed")
    from app.modules.source_management.queue import enqueue_or_run_inline

    job = enqueue_or_run_inline(context, job.id)
    write_audit_event(context, "source.reembed", "ingestion_job", job.id)
    return job


def list_jobs(context: RequestContext) -> list[IngestionJob]:
    rows = current_session().scalars(
        select(IngestionJobRow).where(IngestionJobRow.tenant_id == context.tenant_id).order_by(IngestionJobRow.created_at)
    )
    return [_to_job(job) for job in rows]
