from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class DatabaseSession:
    database_url: str


@contextmanager
def get_db_session(settings: Settings | None = None) -> Iterator[DatabaseSession]:
    resolved = settings or get_settings()
    yield DatabaseSession(database_url=resolved.database_url)
