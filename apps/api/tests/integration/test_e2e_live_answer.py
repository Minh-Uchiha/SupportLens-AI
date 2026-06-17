"""Full end-to-end integration test against real services.

Unlike the rest of the suite (which mocks the LLM and uses fallback embeddings), this test
exercises the real path: add a source, ingest + embed it, start a conversation, ask a
question, and have a real LLM (Ollama via LiteLLM) generate a grounded, cited answer.

It is opt-in and auto-skips unless all of the following are available, so the default
offline suite is unaffected:
  - a real Postgres/pgvector backend (the testcontainer started by conftest),
  - the `sentence-transformers` extra installed (real semantic embeddings),
  - a reachable LiteLLM proxy serving the configured chat model.

Force-enable with SUPPORTLENS_E2E=1 (a missing service then fails instead of skipping),
and point at services with the usual SUPPORTLENS_* env vars (e.g. SUPPORTLENS_LITELLM_BASE_URL,
SUPPORTLENS_LITELLM_MODEL, SUPPORTLENS_EMBEDDING_MODEL).
"""

from __future__ import annotations

import os

import httpx
import pytest

from app.core.config import Settings
from app.modules.llm_gateway import embeddings as embeddings_module

_FORCE = os.environ.get("SUPPORTLENS_E2E") == "1"

# A real, public documentation page used to prove the http/url connector end to end.
_ADOBE_VACATION_URL = "https://benefits.adobe.com/us/time-off/vacation-and-paid-holidays"


def _skip_or_fail(reason: str):
    # When explicitly enabled, a missing dependency is a failure, not a silent skip.
    if _FORCE:
        pytest.fail(f"SUPPORTLENS_E2E=1 but {reason}")
    pytest.skip(reason)


@pytest.fixture
def live_settings(test_settings, is_postgres) -> Settings:
    if not is_postgres:
        _skip_or_fail("real Postgres/pgvector backend is not available")

    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        _skip_or_fail("sentence-transformers is not installed")

    # Live LLM settings layered on top of the real Postgres URL chosen by conftest.
    settings = Settings(
        database_url=test_settings.database_url,
        local_deterministic_llm=False,
    )

    # Probe the LiteLLM proxy so an unreachable model server skips cleanly rather than
    # producing a confusing model_unavailable answer. A 401/403 still means the proxy is
    # up (just auth-gated), so only connection-level failures should skip.
    models_url = settings.litellm_base_url.rstrip("/") + "/models"
    try:
        httpx.get(models_url, timeout=5.0)
    except Exception as exc:
        _skip_or_fail(f"LiteLLM proxy not reachable at {models_url}: {exc}")

    return settings


@pytest.fixture
def live_gateway(monkeypatch, live_settings):
    """Point the LLM gateway and embedding gateway at the live settings.

    The DB session uses the app's test_settings (real Postgres); only the gateway modules,
    which read module-level get_settings(), need to be switched to the live LLM config.
    """
    for target in (
        "app.modules.llm_gateway.service.get_settings",
        "app.modules.llm_gateway.litellm_client.get_settings",
        "app.modules.llm_gateway.embeddings.get_settings",
    ):
        monkeypatch.setattr(target, lambda: live_settings)
    # Drop any cached fallback model so the real embedding model is loaded under live settings.
    embeddings_module._load_sentence_transformer.cache_clear()
    yield live_settings
    embeddings_module._load_sentence_transformer.cache_clear()


def _assert_safe_answer(body: dict, conversation_id: str) -> str:
    """Assert the live LLM round-trip produced a valid, safe answer state.

    A small local model is nondeterministic, so accept any grounded/safe outcome rather
    than a single fixed state; the invariants are that the pipeline classified the result
    safely and that any citations come only from retrieved evidence.
    """
    assert body["conversation_id"] == conversation_id
    assert body["answer_text"].strip()

    state = body["answer_state"]
    # model_unavailable would mean the live LLM never answered, which defeats the test.
    assert state != "model_unavailable", body
    grounded_states = {"answered", "partial"}
    safe_no_citation_states = {"clarification_required", "refused_no_evidence", "citation_validation_failed"}
    assert state in grounded_states | safe_no_citation_states, body

    evidence_chunk_ids = {chunk["chunk_id"] for chunk in body["evidence"]}
    if state in grounded_states:
        # Substantive answers must carry citations drawn only from retrieved evidence.
        assert body["citations"], "a grounded answer must cite retrieved evidence"
        cited_chunk_ids = {citation["chunk_id"] for citation in body["citations"]}
        assert cited_chunk_ids <= evidence_chunk_ids, "citations must come from retrieved evidence"
    else:
        # Clarifications/refusals must not present citations.
        assert body["citations"] == []
    return state


@pytest.mark.e2e
def test_end_to_end_live_answer(client, admin_headers, user_headers, live_gateway):
    knowledge = (
        "Error SL-429 means the tenant has exceeded its support API rate limits. "
        "To resolve SL-429, check the tenant's recent usage in the admin console and "
        "retry the request after the rate-limit backoff window has elapsed."
    )

    # 1. Tenant admin adds and ingests a knowledge source (real chunking + embeddings).
    created = client.post(
        "/v1/admin/sources",
        json={"type": "inline", "name": "Rate Limit Runbook", "connection_ref": knowledge},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    source_id = created.json()["id"]

    sync = client.post(
        f"/v1/admin/sources/{source_id}/sync",
        json={"sync_reason": "initial_sync"},
        headers=admin_headers,
    )
    assert sync.status_code == 200, sync.text
    assert sync.json()["status"] == "completed"

    health = client.get(f"/v1/admin/sources/{source_id}/health", headers=admin_headers).json()
    assert health["chunk_count"] >= 1

    # 2. User starts a conversation.
    conversation = client.post(
        "/v1/conversations",
        json={"title": "Rate limit help"},
        headers=user_headers,
    )
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]

    # 3. User asks a question in that conversation.
    chat = client.post(
        "/v1/chat/messages",
        json={"conversation_id": conversation_id, "message": "How do I resolve error SL-429?"},
        headers=user_headers,
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()

    # 4. The real LLM round-trip produced a valid, safe answer state grounded in evidence.
    assert body["evidence"], "retrieval should have found evidence to ground the answer"
    state = _assert_safe_answer(body, conversation_id)

    # 5. The answer and conversation are persisted and retrievable with the same state.
    answer = client.get(f"/v1/answers/{body['answer_id']}", headers=user_headers)
    assert answer.status_code == 200, answer.text
    assert answer.json()["answer_state"] == state

    detail = client.get(f"/v1/conversations/{conversation_id}", headers=user_headers).json()
    roles = [message["role"] for message in detail["messages"]]
    assert "user" in roles


@pytest.mark.e2e
def test_end_to_end_live_answer_url_source(client, admin_headers, user_headers, live_gateway):
    """End-to-end over a real http/url source: ingest a live web page, then answer from it."""
    # The url connector fetches the page during sync, so skip cleanly if it is unreachable.
    try:
        probe = httpx.get(_ADOBE_VACATION_URL, timeout=15.0, follow_redirects=True, headers={"User-Agent": "SupportLensBot/1.0"})
        if probe.status_code >= 400:
            _skip_or_fail(f"source URL returned HTTP {probe.status_code}: {_ADOBE_VACATION_URL}")
    except Exception as exc:
        _skip_or_fail(f"source URL not reachable ({_ADOBE_VACATION_URL}): {exc}")

    # 1. Tenant admin registers a url source pointing at a real Adobe benefits page.
    created = client.post(
        "/v1/admin/sources",
        json={"type": "url", "name": "Adobe Time Off", "connection_ref": _ADOBE_VACATION_URL},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    source_id = created.json()["id"]

    # 2. Sync fetches, normalizes (HTML stripped), chunks, and embeds the page.
    sync = client.post(
        f"/v1/admin/sources/{source_id}/sync",
        json={"sync_reason": "initial_sync"},
        headers=admin_headers,
    )
    assert sync.status_code == 200, sync.text
    assert sync.json()["status"] == "completed", sync.json()

    health = client.get(f"/v1/admin/sources/{source_id}/health", headers=admin_headers).json()
    assert health["chunk_count"] >= 1, health

    # 3. User starts a conversation and asks a vacation/time-off question.
    conversation = client.post("/v1/conversations", json={"title": "Time off"}, headers=user_headers)
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]

    chat = client.post(
        "/v1/chat/messages",
        json={"conversation_id": conversation_id, "message": "Does Adobe offer paid holidays and company break time off?"},
        headers=user_headers,
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()

    # 4. Retrieval surfaced page content and the live LLM produced a safe, grounded answer.
    assert body["evidence"], "retrieval should have found evidence from the Adobe page"
    state = _assert_safe_answer(body, conversation_id)

    # The retrieved evidence should come from the Adobe page we ingested.
    evidence_text = " ".join(chunk["text"].lower() for chunk in body["evidence"])
    assert any(term in evidence_text for term in ("vacation", "holiday", "time off", "break")), evidence_text[:500]

    answer = client.get(f"/v1/answers/{body['answer_id']}", headers=user_headers)
    assert answer.status_code == 200, answer.text
    assert answer.json()["answer_state"] == state
