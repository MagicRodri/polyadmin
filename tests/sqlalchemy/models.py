import asyncio
import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.pool import NullPool

from polyadmin.core.field import ForeignKeyField
from polyadmin.core.filter import BooleanFilter, ChoiceFilter, DateFilter, EmptyFilter, RelationFilter
from polyadmin.core.relation import Relation
from polyadmin.sqlalchemy import SQLAlchemyModelAdmin


class Base(DeclarativeBase):
    pass


class Kind(enum.Enum):
    FICTION = "fiction"
    SCIENCE = "science"


class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    born: Mapped[date | None] = mapped_column(Date, nullable=True)
    kind: Mapped[Kind] = mapped_column(Enum(Kind), default=Kind.FICTION)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    books: Mapped[list["Book"]] = relationship(back_populates="author", passive_deletes="all")


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("authors.id"), nullable=True)
    author: Mapped[Author | None] = relationship(back_populates="books")


def make_session_factory(path) -> async_sessionmaker:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    return async_sessionmaker(engine)


def seed(factory: async_sessionmaker, *objs) -> None:
    async def run() -> None:
        async with factory() as session:
            session.add_all(objs)
            await session.commit()

    asyncio.run(run())


class AuthorAdmin(SQLAlchemyModelAdmin):
    model = Author
    list_display = ("id", "name", "active", "kind", "born")
    form_fields = ("name", "active", "kind", "born", "nickname", "created")
    search_fields = ("name", "nickname")
    filters = (
        BooleanFilter("active"),
        ChoiceFilter("kind", choices=[("fiction", "Fiction"), ("science", "Science")]),
        EmptyFilter("nickname"),
        DateFilter("born"),
    )


class BookAdmin(SQLAlchemyModelAdmin):
    model = Book
    list_display = ("id", "title", "author")
    form_fields = ("title", "author")
    search_fields = ("title",)
    filters = (RelationFilter("author"),)
    fields = (ForeignKeyField("author", relation=Relation("author", target="authors", display_field="name")),)
