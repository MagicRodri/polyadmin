"""Clients and projects, served from SQLite through polyadmin.contrib.sqlalchemy
rather than from the in-memory repositories in models.py.

The database is a temporary file, created and seeded at import with a
synchronous engine: uvicorn imports this app inside its running event loop,
where asyncio.run is not available. The admin then reads it through
aiosqlite. Client has no relationship back to its projects, so deleting one
still referenced reaches the database, which refuses it.
"""

from __future__ import annotations

import atexit
import os
import tempfile
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    def __str__(self) -> str:
        return self.name


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean)
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"), nullable=True)
    client: Mapped[Client | None] = relationship()


CLIENTS = ("Northwind", "Contoso", "Umbrella")
PROJECTS = (
    ("Apollo", "active", True, date(2026, 11, 1), 0),
    ("Borealis", "planned", True, date(2026, 12, 15), 0),
    ("Cascade", "done", False, date(2026, 3, 1), 1),
    ("Delta", "active", True, None, 1),
    ("Eclipse", "planned", True, date(2027, 1, 10), 2),
    ("Fjord", "planned", True, None, None),
)


def _foreign_keys_on(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def open_projects_database() -> async_sessionmaker:
    fd, path = tempfile.mkstemp(prefix="polyadmin-example-", suffix=".sqlite")
    os.close(fd)
    atexit.register(lambda: os.path.exists(path) and os.remove(path))
    seeding = create_engine(f"sqlite:///{path}")
    event.listen(seeding, "connect", _foreign_keys_on)
    Base.metadata.create_all(seeding)
    with Session(seeding) as session:
        clients = [Client(name=name) for name in CLIENTS]
        session.add_all(clients)
        session.add_all(
            Project(name=name, status=status, active=active, due=due, client=None if owner is None else clients[owner])
            for name, status, active, due, owner in PROJECTS
        )
        session.commit()
    seeding.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
    event.listen(engine.sync_engine, "connect", _foreign_keys_on)
    return async_sessionmaker(engine)
