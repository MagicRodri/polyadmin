"""SQLAlchemyModelAdmin: a ModelAdmin served from a SQLAlchemy 2.x (or SQLModel)
async session. Search, filters, ordering and paging run in SQL; writes load the
row and flush through the ORM, so mapper events fire for every change."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from polyadmin.core.field import Field
from polyadmin.core.model_admin import ModelAdmin, RecordFormError
from polyadmin.core.query import ListRequest
from polyadmin.sqlalchemy.columns import coerce, derive_field
from polyadmin.sqlalchemy.filters import check_translatable, filter_clause


async def _execute(session: Any, statement: Any) -> Any:
    """SQLAlchemy's own AsyncSession.execute, even on a subclass that overrides
    it -- sqlmodel's deprecates execute() in favour of exec(), which returns a
    different result shape."""
    if isinstance(session, AsyncSession):
        return await AsyncSession.execute(session, statement)
    return await session.execute(statement)


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SQLAlchemyModelAdmin(ModelAdmin):
    session_factory: ClassVar[Callable[[], Any] | None] = None
    default_filters: ClassVar[Mapping[str, Any]] = {}

    def __init__(self, session_factory: Callable[[], Any] | None = None) -> None:
        factory = session_factory if session_factory is not None else type(self).session_factory
        if factory is None:
            raise TypeError(f"{type(self).__name__} needs a session_factory.")
        self._session_factory = factory
        self._mapper = sa_inspect(self.model)
        super().__init__()
        for filt in self.filters:
            check_translatable(self, filt)
        for name in self.default_filters:
            if self.column(name) is None:
                raise TypeError(f"{type(self).__name__}.default_filters names no column {name!r}")

    def _build_fields(self) -> dict[str, Field]:
        fields = super()._build_fields()
        declared = {field.name for field in self.fields}
        mapper = sa_inspect(self.model)
        names = [*self.list_display, *self.get_form_fields(), *self.search_fields, *(self.detail_fields or ())]
        for name in names:
            if name in declared or name not in mapper.column_attrs:
                continue
            fields[name] = derive_field(name, mapper.column_attrs[name].columns[0])
        return fields

    def get_pk(self, obj: Any) -> Any:
        return getattr(obj, self._pk_column().key, None)

    def _pk_column(self) -> Any:
        return self._mapper.primary_key[0]

    def column(self, name: str) -> Any | None:
        attr = self._mapper.column_attrs.get(name)
        return attr.columns[0] if attr is not None else None

    def relationship(self, name: str) -> Any | None:
        return self._mapper.relationships.get(name)

    def _eager_options(self) -> list[Any]:
        names = {*self.list_display, *self.get_form_fields(), *(self.detail_fields or ())}
        return [selectinload(getattr(self.model, name)) for name in sorted(names) if self.relationship(name) is not None]

    def _where(self, list_request: ListRequest) -> list[Any]:
        clauses: list[Any] = []
        if list_request.search and self.search_fields:
            pattern = f"%{_escape_like(list_request.search)}%"
            clauses.append(
                or_(*(cast(getattr(self.model, name), String).ilike(pattern, escape="\\") for name in self.search_fields))
            )
        for name, value in self.default_filters.items():
            if name not in list_request.filters:
                clauses.append(getattr(self.model, name) == value)
        for filt in self.filters:
            raw = list_request.filters.get(filt.name)
            if not raw:
                continue
            clause = filter_clause(self, filt, raw)
            if clause is not None:
                clauses.append(clause)
        return clauses

    def _order_by(self, ordering: str | None) -> list[Any]:
        pk = getattr(self.model, self._pk_column().key)
        if ordering:
            name = ordering.lstrip("-")
            if self.column(name) is not None:
                attr = getattr(self.model, name)
                return [attr.desc() if ordering.startswith("-") else attr.asc(), pk.asc()]
        return [pk.asc()]

    async def list_page(self, list_request: ListRequest) -> tuple[list[Any], int]:
        where = self._where(list_request)
        count_stmt = select(func.count()).select_from(self.model).where(*where)
        stmt = (
            select(self.model)
            .where(*where)
            .order_by(*self._order_by(list_request.ordering))
            .options(*self._eager_options())
        )
        offset, limit = list_request.window()
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        async with self._session_factory() as session:
            total = (await _execute(session, count_stmt)).scalar_one()
            rows = (await _execute(session, stmt)).scalars().all()
        return list(rows), total

    def _coerce_pk(self, pk: Any) -> Any:
        return coerce(self._pk_column(), pk)

    async def _load(self, session: Any, pk: Any) -> Any:
        return await session.get(self.model, pk, options=self._eager_options(), populate_existing=True)

    async def get_object(self, pk: Any) -> Any:
        try:
            key = self._coerce_pk(pk)
        except (ValueError, TypeError):
            return None
        if key is None:
            return None
        async with self._session_factory() as session:
            try:
                return await self._load(session, key)
            except DBAPIError:
                return None

    def _assign(self, obj: Any, data: dict[str, Any]) -> None:
        errors: dict[str, list[str]] = {}
        for name, value in data.items():
            rel = self.relationship(name)
            if rel is not None:
                if rel.uselist:
                    raise TypeError(f"{type(self).__name__}: many-to-many field {name!r} is not writable")
                column = next(iter(rel.local_columns))
            else:
                column = self.column(name)
                if column is None:
                    continue
            try:
                setattr(obj, column.key, coerce(column, value))
            except (ValueError, TypeError, KeyError) as exc:
                errors.setdefault(name, []).append(str(exc))
        if errors:
            raise RecordFormError(errors)

    async def _commit(self, session: Any, obj: Any) -> Any:
        try:
            await session.flush()
            pk = self.get_pk(obj)
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise RecordFormError({"": [str(exc.orig)]}) from exc
        return await self._load(session, pk)

    async def create(self, data: dict[str, Any]) -> Any:
        obj = self.model()
        self._assign(obj, data)
        async with self._session_factory() as session:
            session.add(obj)
            return await self._commit(session, obj)

    async def update(self, obj: Any, data: dict[str, Any]) -> Any:
        async with self._session_factory() as session:
            current = await self._load(session, self.get_pk(obj))
            if current is None:
                raise RecordFormError({"": ["The record no longer exists."]})
            self._assign(current, data)
            return await self._commit(session, current)

    async def delete(self, obj: Any) -> None:
        async with self._session_factory() as session:
            current = await session.get(self.model, self.get_pk(obj))
            if current is None:
                return
            await session.delete(current)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise RecordFormError({"": [str(exc.orig)]}) from exc
