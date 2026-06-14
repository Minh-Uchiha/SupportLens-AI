from __future__ import annotations

def scheduled_refresh_job_types() -> list[str]:
    return ["scheduled_refresh", "incremental_update", "retry_failed_sync", "permission_refresh"]
