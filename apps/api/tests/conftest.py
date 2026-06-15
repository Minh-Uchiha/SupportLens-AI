import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import reset_database
from app.main import create_app


@pytest.fixture(scope="session")
def test_settings():
    return Settings(database_url="sqlite+pysqlite:///:memory:")


@pytest.fixture(autouse=True)
def reset_stores(test_settings):
    reset_database(test_settings)


@pytest.fixture
def client(test_settings):
    return TestClient(create_app(test_settings), raise_server_exceptions=False)


@pytest.fixture
def user_headers():
    return {"x-tenant-id": "tenant-a", "x-user-id": "user-a", "x-role": "end_user"}


@pytest.fixture
def admin_headers():
    return {"x-tenant-id": "tenant-a", "x-user-id": "admin-a", "x-role": "tenant_admin,platform_operator"}
