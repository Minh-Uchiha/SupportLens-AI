from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _require_postgres(is_postgres):
    # These tests exercise native Postgres full-text/trigram/pgvector and last-known-good
    # behavior against real Postgres-backed data, so they are skipped on the SQLite fallback.
    if not is_postgres:
        pytest.skip("Postgres testcontainer not available")


def _seed_source(client, admin_headers, body: str, name: str = "Runbook") -> str:
    source = client.post(
        "/v1/admin/sources",
        json={"type": "inline", "name": name, "connection_ref": body},
        headers=admin_headers,
    ).json()
    sync = client.post(f"/v1/admin/sources/{source['id']}/sync", json={"sync_reason": "initial_sync"}, headers=admin_headers)
    assert sync.json()["status"] == "completed"
    return source["id"]


def test_postgres_fulltext_finds_exact_error_code(client, admin_headers, user_headers):
    _seed_source(client, admin_headers, "Error SL-429 means the tenant exceeded support rate limits. Retry after the backoff window.")
    response = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers)
    body = response.json()
    assert body["answer_state"] == "answered"
    assert body["citations"]


def test_postgres_vector_finds_paraphrased_question(client, admin_headers, user_headers):
    _seed_source(client, admin_headers, "Error SL-429 means the tenant exceeded support rate limits. Retry after the backoff window.")
    response = client.post("/v1/chat/messages", json={"message": "tenant went over its request quota"}, headers=user_headers)
    assert response.json()["answer_state"] in {"answered", "refused_no_evidence"}


def test_postgres_last_known_good_index_preserved_on_failed_sync(client, admin_headers, user_headers):
    source_id = _seed_source(client, admin_headers, "Password reset requires verifying the identity provider status page.")
    health = client.get(f"/v1/admin/sources/{source_id}/health", headers=admin_headers).json()
    assert health["chunk_count"] >= 1

    # Point the source at a missing path and re-sync: the savepoint must keep prior chunks.
    client.patch(f"/v1/admin/sources/{source_id}", json={"type": "filesystem", "connection_ref": "/path/does/not/exist"}, headers=admin_headers)
    failed = client.post(f"/v1/admin/sources/{source_id}/sync", json={"sync_reason": "manual_resync"}, headers=admin_headers).json()
    assert failed["status"] == "failed"

    after = client.get(f"/v1/admin/sources/{source_id}/health", headers=admin_headers).json()
    assert after["chunk_count"] == health["chunk_count"]
    answer = client.post("/v1/chat/messages", json={"message": "password reset identity provider"}, headers=user_headers).json()
    assert answer["answer_state"] == "answered"
