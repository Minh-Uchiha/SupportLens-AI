from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.modules.auth_policy.schemas import RequestContext
from app.modules.source_management.models import IngestionJob
from app.modules.source_management.service import run_sync_job

logger = logging.getLogger(__name__)

INGESTION_QUEUE_NAME = "supportlens-ingestion"


def get_queue(settings: Settings | None = None):
    """Return an RQ queue bound to the configured Redis. Imported lazily so the queue
    libraries are only required when async ingestion is actually used."""
    from redis import Redis
    from rq import Queue

    resolved = settings or get_settings()
    connection = Redis.from_url(resolved.redis_url)
    return Queue(INGESTION_QUEUE_NAME, connection=connection)


def enqueue_sync_job(context: RequestContext, job_id: str, settings: Settings | None = None) -> str:
    """Enqueue an ingestion job for a worker and return the RQ job id."""
    resolved = settings or get_settings()
    queue = get_queue(resolved)
    rq_job = queue.enqueue(
        "workers.ingestion.jobs.run_ingestion_job",
        kwargs={"tenant_id": context.tenant_id, "user_id": context.user_id, "job_id": job_id},
        retry=_build_retry(resolved),
    )
    logger.info("Enqueued ingestion job job_id=%s rq_id=%s tenant=%s", job_id, rq_job.id, context.tenant_id)
    return rq_job.id


def _build_retry(settings: Settings):
    """Configure RQ retry with a fixed backoff for transient ingestion failures."""
    from rq import Retry

    intervals = [settings.ingestion_retry_backoff_seconds] * max(settings.ingestion_max_retries, 1)
    return Retry(max=max(settings.ingestion_max_retries, 1), interval=intervals)


def enqueue_or_run_inline(context: RequestContext, job_id: str, settings: Settings | None = None) -> IngestionJob:
    """Run the sync job inline, or hand it to a worker when async ingestion is enabled.

    Inline execution keeps the API response holding the finished job (current behavior and
    what the synchronous tests expect). Async execution returns the still-queued job so the
    chat path never blocks on ingestion.
    """
    resolved = settings or get_settings()
    if not resolved.ingestion_async_enabled:
        return run_sync_job(context, job_id)
    try:
        enqueue_sync_job(context, job_id, resolved)
    except Exception:
        # If Redis is unreachable, fall back to inline execution so a sync still happens
        # rather than silently dropping the job.
        logger.error("Failed to enqueue ingestion job job_id=%s; running inline", job_id, exc_info=True)
        return run_sync_job(context, job_id)
    from app.modules.source_management.service import get_job

    return get_job(context, job_id)
