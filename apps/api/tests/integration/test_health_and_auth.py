def test_health_reports_required_local_services(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database_configured"] is True
    assert body["redis_configured"] is True
    assert body["litellm_configured"] is True
    assert body["embedding_model"]


def test_protected_route_requires_tenant_context(client):
    response = client.get("/v1/conversations")
    assert response.status_code == 401


def test_cross_tenant_conversation_access_fails_closed(client, user_headers):
    created = client.post("/v1/conversations", json={"title": "Tenant A"}, headers=user_headers)
    assert created.status_code == 200
    other_headers = {"x-tenant-id": "tenant-b", "x-user-id": "user-a", "x-role": "end_user"}
    response = client.get(f"/v1/conversations/{created.json()['id']}", headers=other_headers)
    assert response.status_code == 403


def test_role_guard_blocks_non_admin_source_management(client, user_headers):
    response = client.post("/v1/admin/sources", json={"name": "Docs"}, headers=user_headers)
    assert response.status_code == 403
