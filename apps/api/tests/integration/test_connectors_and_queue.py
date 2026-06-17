from __future__ import annotations

import pytest

from app.core.config import Settings
from app.db.session import db_session_scope
from app.modules.auth_policy.schemas import RequestContext, Role
from app.modules.source_management.connectors import load_documents_from_source
from app.modules.source_management.service import (
    SourceCreate,
    SyncRequest,
    create_source,
    get_chunks_for_tenant,
    trigger_sync,
)


def _admin_context() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="admin-a", roles={Role.tenant_admin, Role.platform_operator})


def test_http_connector_strips_html(monkeypatch):
    class _Response:
        text = "<html><head><style>x{}</style></head><body><h1>Reset</h1><p>Use the portal.</p></body></html>"
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    import httpx

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _Response())
    docs = load_documents_from_source("http", "Docs", "https://example.test/reset")
    external_id, title, text = docs[0]
    assert external_id == "https://example.test/reset"
    assert "Reset" in text and "Use the portal." in text
    assert "<" not in text  # markup removed


def test_unsupported_source_type_raises():
    with pytest.raises(ValueError):
        load_documents_from_source("does-not-exist", "x", "y")


def test_async_enqueue_queues_job_without_running_inline(monkeypatch, test_settings):
    # Enable async ingestion and back the RQ queue with fakeredis so no Redis server is needed.
    fakeredis = pytest.importorskip("fakeredis")
    from rq import Queue

    async_settings = Settings(database_url=test_settings.database_url, ingestion_async_enabled=True)
    fake_conn = fakeredis.FakeStrictRedis()

    import app.modules.source_management.queue as queue_module

    # Route enqueue_or_run_inline down the async branch and onto a fakeredis-backed queue.
    monkeypatch.setattr(queue_module, "get_settings", lambda: async_settings)
    monkeypatch.setattr(queue_module, "get_queue", lambda s=None: Queue("supportlens-ingestion", connection=fake_conn))

    with db_session_scope(test_settings):
        context = _admin_context()
        source = create_source(context, SourceCreate(type="inline", name="AsyncKB", connection_ref="Async content for SL-429."))
        job = trigger_sync(context, source.id, SyncRequest(sync_reason="initial_sync"))
        # Async path returns the still-queued job (a worker would run it) and does not
        # process chunks inline, so the chat path never blocks on ingestion.
        assert job.status == "queued"
        assert [c for c in get_chunks_for_tenant(context) if c.source_id == source.id] == []

    # The job is actually sitting on the queue waiting for a worker.
    assert Queue("supportlens-ingestion", connection=fake_conn).count == 1
