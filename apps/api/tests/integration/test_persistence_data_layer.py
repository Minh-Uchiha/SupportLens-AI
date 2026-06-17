from unittest.mock import patch


def test_conversation_persists_across_requests(client, user_headers):
    created = client.post("/v1/conversations", json={"title": "Durable chat"}, headers=user_headers)
    assert created.status_code == 200

    listed = client.get("/v1/conversations", headers=user_headers)
    assert listed.status_code == 200
    assert [item["title"] for item in listed.json()] == ["Durable chat"]


def test_failed_answer_rolls_back_partial_writes(client, admin_headers, user_headers):
    source = client.post(
        "/v1/admin/sources",
        json={
            "type": "inline",
            "name": "Rollback",
            "connection_ref": "Rollback verification evidence should reach the model stage.",
        },
        headers=admin_headers,
    ).json()
    sync = client.post(f"/v1/admin/sources/{source['id']}/sync", json={"sync_reason": "initial_sync"}, headers=admin_headers)
    assert sync.status_code == 200

    with patch("app.modules.answer.service.call_model", side_effect=RuntimeError("forced failure")):
        failed = client.post("/v1/chat/messages", json={"message": "rollback verification evidence"}, headers=user_headers)

    assert failed.status_code == 500
    listed = client.get("/v1/conversations", headers=user_headers)
    assert listed.status_code == 200
    assert listed.json() == []
