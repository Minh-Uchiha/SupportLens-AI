from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.db.models import Base
from app.db.session import get_engine, reset_database
from app.main import create_app

logger = logging.getLogger(__name__)

_API_DIR = Path(__file__).resolve().parent.parent


def _try_start_postgres() -> tuple[str, object] | None:
    """Start a pgvector Postgres testcontainer and return (url, container), or None.

    Returns None whenever Docker or the testcontainers package is unavailable so the suite
    transparently falls back to SQLite (the previous behavior).
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except Exception:
        logger.info("testcontainers not installed; using SQLite test backend")
        return None
    try:
        container = PostgresContainer("pgvector/pgvector:pg16", driver="psycopg")
        container.start()
    except Exception:
        logger.info("Could not start Postgres testcontainer (Docker unavailable); using SQLite")
        return None
    return container.get_connection_url(), container


def _run_migrations(database_url: str) -> None:
    """Apply Alembic migrations against the Postgres container so FTS/trigram/pgvector exist."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_API_DIR),
        check=True,
        env={"SUPPORTLENS_DATABASE_URL": database_url, "PATH": _env_path()},
    )


def _env_path() -> str:
    import os

    return os.environ.get("PATH", "")


@pytest.fixture(scope="session")
def postgres_backend():
    """Session-wide Postgres container info, or None when running on SQLite."""
    started = _try_start_postgres()
    if started is None:
        yield None
        return
    database_url, container = started
    try:
        _run_migrations(database_url)
        yield database_url
    finally:
        container.stop()


@pytest.fixture(scope="session")
def test_settings(postgres_backend):
    if postgres_backend is not None:
        return Settings(database_url=postgres_backend)
    return Settings(database_url="sqlite+pysqlite:///:memory:")


@pytest.fixture(scope="session")
def is_postgres(test_settings) -> bool:
    return test_settings.database_url.startswith("postgresql")


@pytest.fixture(autouse=True)
def reset_stores(test_settings, is_postgres):
    if is_postgres:
        # Migrations already created the schema (including FTS/trigram/vector); just clear
        # data between tests with a single cascading truncate.
        _truncate_all(test_settings)
    else:
        # SQLite has no migration-managed extras, so drop/create from the ORM metadata.
        reset_database(test_settings)


def _truncate_all(settings: Settings) -> None:
    engine = get_engine(settings.database_url)
    table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE {} RESTART IDENTITY CASCADE".format(", ".join(table_names))))


@pytest.fixture
def client(test_settings):
    return TestClient(create_app(test_settings), raise_server_exceptions=False)


@pytest.fixture
def user_headers():
    return {"x-tenant-id": "tenant-a", "x-user-id": "user-a", "x-role": "end_user"}


@pytest.fixture
def admin_headers():
    return {"x-tenant-id": "tenant-a", "x-user-id": "admin-a", "x-role": "tenant_admin,platform_operator"}
