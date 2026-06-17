from __future__ import annotations

import app.modules.source_management.service as source_service
from app.db.session import db_session_scope
from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.source_management.connectors import register_connector
from app.modules.source_management.service import (
    SourceCreate,
    SourcePatch,
    SyncRequest,
    create_source,
    get_chunks_for_tenant,
    reembed_source,
    run_sync_job,
    trigger_sync,
    update_source,
    _enqueue_job,
)
from workers.ingestion.jobs import run_ingestion_job
from workers.scheduler.sync_scheduler import enqueue_scheduled_refreshes


def _admin_context() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="admin-a", roles={Role.tenant_admin, Role.platform_operator})


def _seed_inline_source(context: RequestContext, body: str = "SL-429 means the tenant exceeded support rate limits.") -> str:
    source = create_source(context, SourceCreate(type="inline", name="Runbook", connection_ref=body))
    trigger_sync(context, source.id, SyncRequest(sync_reason="initial_sync"))
    return source.id


def test_cleanup_removes_chunks(test_settings):
    with db_session_scope(test_settings):
        context = _admin_context()
        source_id = _seed_inline_source(context)
        assert get_chunks_for_tenant(context)

        job = _enqueue_job(context, source_id, "cleanup_source", "disable")
        result = run_sync_job(context, job.id)
        assert result.status == "completed"
        assert [chunk for chunk in get_chunks_for_tenant(context) if chunk.source_id == source_id] == []


def test_permission_refresh_updates_acl(test_settings):
    with db_session_scope(test_settings):
        context = _admin_context()
        source_id = _seed_inline_source(context)
        update_source(context, source_id, SourcePatch(permission_mode="restricted"))

        job = _enqueue_job(context, source_id, "permission_refresh", "schedule")
        result = run_sync_job(context, job.id)
        assert result.status == "completed"
        chunks = [chunk for chunk in get_chunks_for_tenant(context) if chunk.source_id == source_id]
        assert chunks and all(chunk.acl_metadata.get("permission_mode") == "restricted" for chunk in chunks)


def test_incremental_update_applies_changed_content(test_settings):
    with db_session_scope(test_settings):
        context = _admin_context()
        source_id = _seed_inline_source(context, body="Original content about error ABC-1.")
        update_source(context, source_id, SourcePatch(connection_ref="Updated content about error XYZ-9 backoff."))

        job = _enqueue_job(context, source_id, "incremental_update", "delta")
        result = run_sync_job(context, job.id)
        assert result.status == "completed"
        texts = " ".join(chunk.text for chunk in get_chunks_for_tenant(context) if chunk.source_id == source_id)
        assert "XYZ-9" in texts and "ABC-1" not in texts


def test_reembed_refreshes_only_stale_chunks(test_settings, monkeypatch):
    with db_session_scope(test_settings):
        context = _admin_context()
        source_id = _seed_inline_source(context)
        chunks_before = [c for c in get_chunks_for_tenant(context) if c.source_id == source_id]
        assert chunks_before and all(c.embedding for c in chunks_before)

        # Bump the reported embedding version so existing chunks look stale.
        monkeypatch.setattr(source_service, "current_embedding_version", lambda: "999")
        job = reembed_source(context, source_id)
        assert job.status == "completed"
        chunks_after = [c for c in get_chunks_for_tenant(context) if c.source_id == source_id]
        assert chunks_after and all(c.embedding_version == "999" for c in chunks_after)


def test_retry_then_success_keeps_last_known_good(test_settings):
    with db_session_scope(test_settings):
        context = _admin_context()
        source_id = _seed_inline_source(context, body="Stable runbook content for SL-429 retries.")
        good_chunks = [c.text for c in get_chunks_for_tenant(context) if c.source_id == source_id]

        # Point the source at a missing path so the next sync fails; the savepoint must keep
        # the previously indexed chunks intact (last-known-good behavior under retry).
        update_source(context, source_id, SourcePatch(type="filesystem", connection_ref="/does/not/exist"))
        failed_job = _enqueue_job(context, source_id, "retry_failed_sync", "retry")
        failed = run_sync_job(context, failed_job.id)
        assert failed.status == "failed"
        preserved = [c.text for c in get_chunks_for_tenant(context) if c.source_id == source_id]
        assert preserved == good_chunks

        # A subsequent successful retry (valid inline source again) replaces the index.
        update_source(context, source_id, SourcePatch(type="inline", connection_ref="Recovered content for SL-429."))
        retry_job = _enqueue_job(context, source_id, "retry_failed_sync", "retry")
        recovered = run_sync_job(context, retry_job.id)
        assert recovered.status == "completed"
        recovered_text = " ".join(c.text for c in get_chunks_for_tenant(context) if c.source_id == source_id)
        assert "Recovered content" in recovered_text


def test_worker_entrypoint_runs_job_in_own_session(test_settings, monkeypatch):
    # Force the worker job handler to use the test database instead of the default settings.
    import workers.ingestion.jobs as worker_jobs

    monkeypatch.setattr(worker_jobs, "get_settings", lambda: test_settings)
    with db_session_scope(test_settings):
        context = _admin_context()
        source = create_source(context, SourceCreate(type="inline", name="WorkerKB", connection_ref="Worker path content."))
        job = _enqueue_job(context, source.id, "initial_sync", "initial_sync")
        job_id = job.id

    # The handler opens its own session scope, mimicking execution on an RQ worker.
    result = run_ingestion_job("tenant-a", "admin-a", job_id)
    assert result["status"] == "completed"


def test_scheduled_refresh_enqueues_due_sources(test_settings, monkeypatch):
    enqueued: list[str] = []
    monkeypatch.setattr(
        "workers.scheduler.sync_scheduler.enqueue_sync_job",
        lambda context, job_id, settings=None: enqueued.append(job_id) or "rq-1",
    )
    with db_session_scope(test_settings):
        context = _admin_context()
        # Only the scheduled-policy source should be picked up; manual stays untouched.
        create_source(context, SourceCreate(type="inline", name="Auto", connection_ref="auto", sync_policy="scheduled"))
        create_source(context, SourceCreate(type="inline", name="Manual", connection_ref="manual", sync_policy="manual"))

    job_ids = enqueue_scheduled_refreshes(test_settings)
    assert len(job_ids) == 1
    assert enqueued == job_ids


def test_connector_registry_supports_custom_type(test_settings):
    register_connector("memdoc", lambda name, ref: [("mem-1", name, f"custom {ref}")])
    with db_session_scope(test_settings):
        context = _admin_context()
        source = create_source(context, SourceCreate(type="memdoc", name="Mem", connection_ref="payload"))
        result = trigger_sync(context, source.id, SyncRequest(sync_reason="initial_sync"))
        assert result.status == "completed"
        texts = " ".join(c.text for c in get_chunks_for_tenant(context) if c.source_id == source.id)
        assert "custom payload" in texts
