"""The list query pipeline: search -> filters -> ordering.

`execute_list_query` is deliberately independent of pagination so the
same filtered/ordered result set can back the list view, an export, or
a custom action -- each decides separately whether to paginate it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ListRequest:
    search: str | None = None
    filters: dict[str, str] = field(default_factory=dict)
    ordering: str | None = None
    page: int = 1
    page_size: int = 25


def apply_search(model_admin: Any, objects: list[Any], search: str | None) -> list[Any]:
    if not search:
        return objects
    term = search.lower()
    fields = [model_admin.get_field(name) for name in model_admin.search_fields]
    if not fields:
        return objects

    def matches(obj: Any) -> bool:
        return any(term in str(f.get_value(obj)).lower() for f in fields if f.get_value(obj) is not None)

    return [obj for obj in objects if matches(obj)]


def apply_filters(model_admin: Any, objects: list[Any], raw_filters: dict[str, str]) -> list[Any]:
    for filt in model_admin.filters:
        if filt.name in raw_filters:
            objects = filt.apply(objects, raw_filters[filt.name], model_admin)
    return objects


def apply_ordering(model_admin: Any, objects: list[Any], ordering: str | None) -> list[Any]:
    if not ordering:
        return objects
    reverse = ordering.startswith("-")
    name = ordering[1:] if reverse else ordering
    try:
        target_field = model_admin.get_field(name)
    except KeyError:
        return objects

    def sort_key(obj: Any) -> tuple[bool, Any]:
        value = target_field.get_value(obj)
        # None-safe: push None values to the end regardless of direction.
        return (value is None, value)

    return sorted(objects, key=sort_key, reverse=reverse)


def execute_list_query(model_admin: Any, objects: list[Any], list_request: ListRequest) -> list[Any]:
    objects = apply_search(model_admin, objects, list_request.search)
    objects = apply_filters(model_admin, objects, list_request.filters)
    objects = apply_ordering(model_admin, objects, list_request.ordering)
    return objects
