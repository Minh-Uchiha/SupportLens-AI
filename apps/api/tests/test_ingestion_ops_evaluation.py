def test_source_health_and_failed_sync_preserve_last_good_index(client, admin_headers, user_headers):
    source = client.post(
        "/v1/admin/sources",
        json={"type": "inline", "name": "KB", "connection_ref": "Password reset errors require verifying the identity provider status page."},
        headers=admin_headers,
    ).json()
    client.post(f"/v1/admin/sources/{source['id']}/sync", json={"sync_reason": "initial_sync"}, headers=admin_headers)
    health = client.get(f"/v1/admin/sources/{source['id']}/health", headers=admin_headers).json()
    assert health["chunk_count"] == 1
    assert health["freshness"] == "fresh"

    client.patch(f"/v1/admin/sources/{source['id']}", json={"type": "filesystem", "connection_ref": "/path/that/does/not/exist"}, headers=admin_headers)
    failed = client.post(f"/v1/admin/sources/{source['id']}/sync", json={"sync_reason": "manual_resync"}, headers=admin_headers).json()
    assert failed["status"] == "failed"
    answer = client.post("/v1/chat/messages", json={"message": "password reset identity provider"}, headers=user_headers).json()
    assert answer["answer_state"] == "answered"


def test_operator_trace_audit_usage_and_launch_quality(client, admin_headers, user_headers):
    source = client.post(
        "/v1/admin/sources",
        json={"type": "inline", "name": "Ops", "connection_ref": "Citation failures must return a safe refusal instead of unsupported generation."},
        headers=admin_headers,
    ).json()
    client.post(f"/v1/admin/sources/{source['id']}/sync", json={"sync_reason": "initial_sync"}, headers=admin_headers)
    answer = client.post("/v1/chat/messages", json={"message": "What happens on citation failures?"}, headers=user_headers).json()

    trace = client.get(f"/v1/operator/traces/{answer['trace_id']}", headers=admin_headers)
    assert trace.status_code == 200
    stages = [stage["stage"] for stage in trace.json()["stages"]]
    assert {"policy", "retrieval", "model", "citation_validation"}.issubset(stages)

    audit = client.get("/v1/operator/audit", headers=admin_headers).json()
    assert any(event["action"] == "source.create" for event in audit)

    feedback = client.post(
        "/v1/feedback",
        json={"answer_id": answer["answer_id"], "feedback_type": "helpful", "comment": "Good citation"},
        headers=user_headers,
    )
    assert feedback.status_code == 200

    eval_set = client.post("/v1/evaluation/sets", json={"name": "launch", "scenario_count": 4}, headers=admin_headers).json()
    results = client.post(f"/v1/evaluation/sets/{eval_set['id']}/run", headers=admin_headers).json()
    assert {item["metric"] for item in results} == {"groundedness", "citation_correctness", "retrieval_relevance", "refusal_correctness"}

    launch = client.get("/v1/evaluation/launch-gate", headers=admin_headers).json()
    assert launch["ready"] is True
