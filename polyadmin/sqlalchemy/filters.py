"""Translating polyadmin's filters into SQL WHERE clauses. Each translation
mirrors the in-memory `Filter.apply` it replaces, so a list reads the same
whichever side resolves it."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import and_, false, or_

from polyadmin.core.filter import (
    EMPTY_FILTER_EMPTY,
    EMPTY_FILTER_NOT_EMPTY,
    BooleanFilter,
    ChoiceFilter,
    DateFilter,
    EmptyFilter,
    RelationFilter,
    date_filter_range,
)
from polyadmin.sqlalchemy.columns import coerce, python_type

_TRUE = {"true", "1", "on", "yes"}
_SUPPORTED = (BooleanFilter, ChoiceFilter, EmptyFilter, DateFilter, RelationFilter)


def check_translatable(model_admin: Any, filt: Any) -> None:
    if not isinstance(filt, _SUPPORTED):
        raise TypeError(
            f"{type(model_admin).__name__} filter {filt.name!r} ({type(filt).__name__}) has no SQL translation"
        )
    if model_admin.column(filt.name) is None and model_admin.relationship(filt.name) is None:
        raise TypeError(f"{type(model_admin).__name__} filter {filt.name!r} names no column or relationship")


def _safe_coerce(column: Any, raw: str) -> tuple[bool, Any]:
    try:
        return True, coerce(column, raw)
    except (ValueError, TypeError, KeyError):
        return False, None


def _relation_clause(model_admin: Any, filt: Any, raw_value: str) -> Any:
    model = model_admin.model
    rel = model_admin.relationship(filt.name)
    if rel is not None and rel.uselist:
        target_pk = rel.mapper.primary_key[0]
        ok, value = _safe_coerce(target_pk, raw_value)
        return getattr(model, filt.name).any(target_pk == value) if ok else false()
    column = model_admin.column(filt.name)
    local = column if column is not None else next(iter(rel.local_columns))
    ok, value = _safe_coerce(local, raw_value)
    return (getattr(model, local.key) == value) if ok else false()


def _empty_clause(model_admin: Any, filt: Any, raw_value: str) -> Any:
    if raw_value not in (EMPTY_FILTER_EMPTY, EMPTY_FILTER_NOT_EMPTY):
        return None
    model = model_admin.model
    rel = model_admin.relationship(filt.name)
    attr = getattr(model, filt.name)
    if rel is not None:
        empty = ~attr.any() if rel.uselist else getattr(model, next(iter(rel.local_columns)).key).is_(None)
    elif python_type(model_admin.column(filt.name)) is str:
        empty = or_(attr.is_(None), attr == "")
    else:
        empty = attr.is_(None)
    return empty if raw_value == EMPTY_FILTER_EMPTY else ~empty


def filter_clause(model_admin: Any, filt: Any, raw_value: str) -> Any:
    if isinstance(filt, RelationFilter):
        return _relation_clause(model_admin, filt, raw_value)
    if isinstance(filt, EmptyFilter):
        return _empty_clause(model_admin, filt, raw_value)

    column = model_admin.column(filt.name)
    attr = getattr(model_admin.model, filt.name)

    if isinstance(filt, BooleanFilter):
        if raw_value.lower() in _TRUE:
            return attr.is_(True)
        return or_(attr.is_(False), attr.is_(None))

    if isinstance(filt, ChoiceFilter):
        ok, value = _safe_coerce(column, raw_value)
        return (attr == value) if ok else false()

    if isinstance(filt, DateFilter):
        window = date_filter_range(raw_value, datetime.now())
        if window is None:
            return None
        start, end = window
        if python_type(column) is datetime:
            start, end = datetime.combine(start, time.min), datetime.combine(end, time.min)
        return and_(attr >= start, attr < end)

    return None
