"""SQLAlchemy engine/session plumbing and shared column mixins.

SQLite is the single source of truth for the whole system. Every table uses a
UUID string primary key and carries ``created_at`` / ``updated_at`` timestamps.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import DateTime, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDMixin:
    """Adds a string UUID primary key."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TimestampMixin:
    """Adds created/updated timestamps maintained by the ORM."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Database:
    """Owns the engine and hands out sessions.

    Usage::

        db = Database(settings.storage.sqlite_path)
        db.create_all()
        with db.session() as session:
            ...
    """

    def __init__(self, sqlite_path: Path | str, *, echo: bool = False) -> None:
        self.path = Path(sqlite_path)
        if str(sqlite_path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{self.path}"
        else:
            url = "sqlite://"
        self.engine: Engine = create_engine(url, echo=echo, future=True)
        _enable_sqlite_fk(self.engine)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        # Import models so they register on Base.metadata before create_all.
        from job_agent.database import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    def session(self) -> Session:
        return self._session_factory()

    def session_scope(self) -> _SessionScope:
        return _SessionScope(self._session_factory)


class _SessionScope:
    """Context manager that commits on success and rolls back on error."""

    def __init__(self, factory: sessionmaker) -> None:
        self._factory = factory
        self._session: Session | None = None

    def __enter__(self) -> Session:
        self._session = self._factory()
        return self._session

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self._session is not None
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()


def _enable_sqlite_fk(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, _: object) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def iter_session(db: Database) -> Iterator[Session]:  # pragma: no cover - convenience
    session = db.session()
    try:
        yield session
    finally:
        session.close()
