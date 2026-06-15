from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Iterator

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.models import Base


_current_session: ContextVar[Session | None] = ContextVar("supportlens_db_session", default=None)


@lru_cache
def get_engine(database_url: str) -> Engine:
    kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)


@lru_cache
def get_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), autoflush=False, expire_on_commit=False, future=True)


def current_session() -> Session:
    session = _current_session.get()
    if session is None:
        raise RuntimeError("No database session is bound to the current request")
    return session


def get_db_session(settings: Settings | None = None) -> Iterator[Session]:
    resolved = settings or get_settings()
    session = get_session_factory(resolved.database_url)()
    token = _current_session.set(session)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _current_session.reset(token)
        session.close()


db_session_scope = contextmanager(get_db_session)


def db_session_dependency(request: Request) -> Iterator[Session]:
    settings = getattr(request.app.state, "settings", None)
    yield from get_db_session(settings)


def check_database(settings: Settings | None = None) -> bool:
    with db_session_scope(settings) as session:
        session.execute(text("SELECT 1"))
    return True


def reset_database(settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    engine = get_engine(resolved.database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
