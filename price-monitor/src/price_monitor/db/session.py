from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any, cast

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from price_monitor.config import get_settings
from price_monitor.db.base import Base

SessionFactory = sessionmaker[Session]


def normalize_database_url(database_url: str | URL) -> URL:
    """Select psycopg 3 for otherwise driver-less PostgreSQL URLs."""

    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        return url.set(drivername="postgresql+psycopg")
    return url


def create_db_engine(
    database_url: str | URL | None = None,
    *,
    echo: bool = False,
) -> Engine:
    url = normalize_database_url(database_url or get_settings().database_url)
    options: dict[str, Any] = {"echo": echo, "pool_pre_ping": True}

    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
        if url.database in {None, "", ":memory:"}:
            options["poolclass"] = StaticPool

    db_engine = create_engine(url, **options)

    if url.get_backend_name() == "sqlite":

        @event.listens_for(db_engine, "connect")
        def _enable_sqlite_foreign_keys(
            dbapi_connection: Any,
            connection_record: Any,
        ) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return db_engine


def create_session_factory(db_engine: Engine) -> SessionFactory:
    return sessionmaker(
        bind=db_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


engine = create_db_engine()
SessionLocal = create_session_factory(engine)


@contextmanager
def session_scope(
    session_factory: SessionFactory = SessionLocal,
) -> Iterator[Session]:
    """Commit a unit of work, rolling it back before propagating failures."""

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that owns and closes a request-scoped session."""

    session_factory = cast(
        SessionFactory,
        getattr(request.app.state, "session_factory", SessionLocal),
    )
    with session_factory() as session:
        yield session


def get_session() -> Generator[Session, None, None]:
    """Framework-independent session generator using the process default."""

    with SessionLocal() as session:
        yield session


def create_schema(db_engine: Engine = engine) -> None:
    Base.metadata.create_all(db_engine)


def drop_schema(db_engine: Engine = engine) -> None:
    Base.metadata.drop_all(db_engine)
