def _seed_source(client, admin_headers):
    source = client.post(
        "/v1/admin/sources",
        json={
            "type": "inline",
            "name": "Runbook",
            "connection_ref": "Error SL-429 means the tenant has exceeded support rate limits. Resolve it by checking usage and retrying after the backoff window. SupportLens AI requires citations for every substantive support answer.",
        },
        headers=admin_headers,
    )
    assert source.status_code == 200
    source_id = source.json()["id"]
    sync = client.post(f"/v1/admin/sources/{source_id}/sync", json={"sync_reason": "initial_sync"}, headers=admin_headers)
    assert sync.status_code == 200
    assert sync.json()["status"] == "completed"
    return source_id


def test_seeded_chat_returns_validated_citation(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    response = client.post("/v1/chat/messages", json={"message": "How do I resolve SL-429?"}, headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["answer_state"] == "answered"
    assert body["citations"]
    assert body["citations"][0]["citation_anchor"].startswith("Runbook#chunk")


def test_no_evidence_refuses_without_hallucinating(client, user_headers):
    response = client.post("/v1/chat/messages", json={"message": "What is a completely absent topic?"}, headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["answer_state"] == "refused_no_evidence"
    assert body["citations"] == []


def test_model_unavailable_returns_safe_state(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    response = client.post("/v1/chat/messages", json={"message": "simulate_model_unavailable SL-429"}, headers=user_headers)
    assert response.status_code == 200
    assert response.json()["answer_state"] == "model_unavailable"


def test_paraphrased_retrieval_finds_rate_limit_runbook(client, admin_headers, user_headers):
    _seed_source(client, admin_headers)
    response = client.post("/v1/chat/messages", json={"message": "tenant exceeded rate limits backoff"}, headers=user_headers)
    assert response.status_code == 200
    assert response.json()["answer_state"] == "answered"
