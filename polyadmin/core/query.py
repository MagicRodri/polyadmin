"""The list query pipeline: search -> filters -> ordering.

`execute_list_query` is deliberately independent of pagination so the
same filtered/ordered result set can back the list view, an export, or
a custom action -- each decides separately whether to paginate it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


# The size assumed when a request names none. Matches the handlers' own
# query-string default, so a ListRequest built by hand and one parsed
# from a URL page the same way.
DEFAULT_PAGE_SIZE = 25


@dataclass
class ListRequest:
    search: str | None = None
    filters: dict[str, str] = field(default_factory=dict)
    ordering: str | None = None
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    # unlimited asks for every matching row rather than one page -- what
    # an export wants. It overrides page/page_size rather than being
    # expressed as page_size 0, so "unset" and "all" stay
    # distinguishable.
    unlimited: bool = False

    def window(self) -> tuple[int, int]:
        """The (offset, limit) pair a data source wants. A limit of 0
        means no limit -- see `unlimited`.
        """
        if self.unlimited:
            return 0, 0
        size = self.page_size if self.page_size and self.page_size >= 1 else DEFAULT_PAGE_SIZE
        page = self.page if self.page and self.page >= 1 else 1
        return (page - 1) * size, size


class ListQuerier(Protocol):
    """An optional ModelAdmin capability. Implement `list_page` to
    resolve the whole list query -- search, filters, ordering and the
    page window -- in the data source itself, typically as one SQL
    query, instead of letting the framework do it in memory over
    everything get_queryset returns.

    It is all-or-nothing by design: when a ModelAdmin implements this,
    the framework applies *nothing* further, because it cannot tell what
    the implementation already did and re-applying would double-filter.
    The returned total is the count of rows matching search+filters
    before the window, which is what pagination displays.

    A ModelAdmin that does not implement it keeps the in-memory path,
    unchanged.
    """

    def list_page(self, list_request: ListRequest) -> tuple[list[Any], int]:
        ...


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


def list_objects(model_admin: Any, list_request: ListRequest) -> tuple[list[Any], int]:
    """Resolve a list query, and the only place that decides how.

    A ModelAdmin implementing `list_page` answers it itself -- one query
    in its own data source, with nothing re-applied here, because we
    cannot tell what it already did. Everything else falls back to
    loading the queryset and filtering it in memory.

    Every consumer goes through here (list view, both exports, the
    autocomplete lookup, relation option lists), so the two paths cannot
    drift: the request's window is what distinguishes "one page" from
    "capped at 20" from "every matching row".

    Returns the objects for the requested window and the total matching
    rows before it, which is what pagination needs.
    """
    if hasattr(model_admin, "list_page"):
        return model_admin.list_page(list_request)
    objects = execute_list_query(model_admin, model_admin.get_queryset(), list_request)
    total = len(objects)
    offset, limit = list_request.window()
    offset = min(offset, total)
    end = total if limit == 0 else min(offset + limit, total)
    return objects[offset:end], total
