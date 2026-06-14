from __future__ import annotations

from app.modules.auth_policy.schemas import RequestContext
from app.modules.source_management.service import run_sync_job


def run_ingestion_job(context: RequestContext, job_id: str):
    return run_sync_job(context, job_id)
