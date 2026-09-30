"""Column introspection: the Field a column implies, and coercion of submitted
form values into the column's Python type."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from polyadmin.core.field import (
    BooleanField,
    DateField,
    DateTimeField,
    DecimalField,
    EnumField,
    Field,
    IntegerField,
    StringField,
)

_TRUE = {"true", "1", "on", "yes"}


def python_type(column: Any) -> type | None:
    try:
        return column.type.python_type
    except NotImplementedError:
        return None


def enum_class(column: Any) -> type | None:
    return getattr(column.type, "enum_class", None)


def is_required(column: Any) -> bool:
    return (
        not column.nullable
        and not column.primary_key
        and column.default is None
        and column.server_default is None
    )


def derive_field(name: str, column: Any) -> Field:
    required = is_required(column)
    enum_cls = enum_class(column)
    if enum_cls is not None:
        return EnumField(name, choices=[member.value for member in enum_cls], required=required)
    py = python_type(column)
    if py is bool:
        return BooleanField(name)
    if py is int:
        return IntegerField(name, required=required)
    if py in (float, Decimal):
        return DecimalField(name, required=required)
    if py is datetime:
        return DateTimeField(name, required=required)
    if py is date:
        return DateField(name, required=required)
    if py is str:
        return StringField(name, required=required)
    return Field(name, required=required)


def coerce(column: Any, value: Any) -> Any:
    if value is None or value == "":
        return None
    enum_cls = enum_class(column)
    if enum_cls is not None:
        if isinstance(value, enum_cls):
            return value
        try:
            return enum_cls(value)
        except ValueError:
            if isinstance(value, str) and value.lstrip("-").isdigit():
                return enum_cls(int(value))
            if isinstance(value, str) and value in enum_cls.__members__:
                return enum_cls[value]
            raise
    py = python_type(column)
    if py is bool:
        return value.lower() in _TRUE if isinstance(value, str) else bool(value)
    if py is int and not isinstance(value, bool):
        return int(value)
    if py in (float, Decimal) and isinstance(value, str):
        return py(value)
    if py is datetime and isinstance(value, str):
        return datetime.fromisoformat(value)
    if py is date and isinstance(value, str):
        return date.fromisoformat(value)
    return value
