from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.models import IngestionJobRow, KnowledgeSourceRow
from app.db.session import db_session_scope
from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.source_management.queue import enqueue_sync_job

logger = logging.getLogger(__name__)

# Sources configured to refresh automatically. "manual" sources are excluded because they
# only sync when an admin explicitly triggers them.
_AUTO_SYNC_POLICIES = {"scheduled", "incremental", "auto", "hourly", "daily"}


def scheduled_refresh_job_types() -> list[str]:
    return ["scheduled_refresh", "incremental_update", "retry_failed_sync", "permission_refresh"]


def _due_sources(session) -> list[KnowledgeSourceRow]:
    rows = session.scalars(
        select(KnowledgeSourceRow).where(KnowledgeSourceRow.status == "enabled")
    ).all()
    # Only enabled sources with an automatic policy are due for a scheduled refresh.
    return [row for row in rows if row.sync_policy in _AUTO_SYNC_POLICIES]


def enqueue_scheduled_refreshes(settings: Settings | None = None) -> list[str]:
    """Scan enabled, auto-sync sources and enqueue a scheduled_refresh job for each.

    Returns the list of ingestion job ids created. Intended to be invoked periodically
    (for example by RQ's scheduler or an external cron) so stale content gets refreshed.
    """
    resolved = settings or get_settings()
    enqueued_job_ids: list[str] = []
    with db_session_scope(resolved) as session:
        due = _due_sources(session)
        logger.info("Scheduler found %d due sources", len(due))
        for source in due:
            job = IngestionJobRow(
                id=str(uuid4()),
                tenant_id=source.tenant_id,
                source_id=source.id,
                job_type="scheduled_refresh",
                reason="scheduled_refresh",
            )
            session.add(job)
            session.flush()
            context = RequestContext(
                tenant_id=source.tenant_id,
                user_id="scheduler",
                roles={Role.platform_operator, Role.tenant_admin},
            )
            try:
                enqueue_sync_job(context, job.id, resolved)
                enqueued_job_ids.append(job.id)
            except Exception:
                # A queue failure for one source should not abort the whole scan.
                logger.error("Failed to enqueue scheduled refresh source_id=%s", source.id, exc_info=True)
    logger.info("Scheduler enqueued %d scheduled refresh jobs", len(enqueued_job_ids))
    return enqueued_job_ids
