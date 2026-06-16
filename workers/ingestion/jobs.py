from __future__ import annotations

import logging

from app.core.config import get_settings
from app.db.session import db_session_scope
from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.source_management.service import run_sync_job

logger = logging.getLogger(__name__)


def _worker_context(tenant_id: str, user_id: str) -> RequestContext:
    """Rebuild a request context for a job running outside an HTTP request.

    Ingestion jobs are tenant-scoped operations, so the worker grants operator/admin roles
    for the originating tenant. Tenant isolation is still enforced because run_sync_job
    checks that the job and source belong to this tenant.
    """
    return RequestContext(
        tenant_id=tenant_id,
        user_id=user_id or "ingestion-worker",
        roles={Role.platform_operator, Role.tenant_admin},
    )


def run_ingestion_job(tenant_id: str, user_id: str, job_id: str):
    """RQ entrypoint: open a dedicated DB session and run one ingestion job.

    A failure here is re-raised so RQ records the job as failed and applies its retry
    policy; the database transaction rolls back via the session scope.
    """
    settings = get_settings()
    logger.info("Worker picked up ingestion job job_id=%s tenant=%s", job_id, tenant_id)
    try:
        with db_session_scope(settings):
            context = _worker_context(tenant_id, user_id)
            job = run_sync_job(context, job_id)
            logger.info("Worker finished ingestion job job_id=%s status=%s", job_id, job.status)
            return {"job_id": job.id, "status": job.status}
    except Exception:
        logger.error("Worker ingestion job raised job_id=%s tenant=%s", job_id, tenant_id, exc_info=True)
        raise
