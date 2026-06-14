import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.conversation.service import reset_conversation_store
from app.modules.evaluation.service import reset_evaluation_store
from app.modules.source_management.service import reset_source_store
from app.modules.telemetry.service import reset_telemetry_store


@pytest.fixture(autouse=True)
def reset_stores():
    reset_conversation_store()
    reset_source_store()
    reset_telemetry_store()
    reset_evaluation_store()


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def user_headers():
    return {"x-tenant-id": "tenant-a", "x-user-id": "user-a", "x-role": "end_user"}


@pytest.fixture
def admin_headers():
    return {"x-tenant-id": "tenant-a", "x-user-id": "admin-a", "x-role": "tenant_admin,platform_operator"}
