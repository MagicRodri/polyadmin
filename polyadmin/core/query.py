"""The list query pipeline: search -> filters -> ordering.

`execute_list_query` is independent of pagination so the same filtered and
ordered result set can back the list view, an export, or a custom action, each
deciding separately whether to paginate it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from urllib.parse import quote

from polyadmin.core._async import maybe_await

# The size assumed when a request names none, matching the handlers'
# query-string default so a hand-built ListRequest pages like a parsed
# one.
DEFAULT_PAGE_SIZE = 25

# Stands in for a None or blank value: an em dash reads as "nothing here"
# rather than as a cell that failed to render.
DEFAULT_EMPTY_VALUE = "\u2014"


@dataclass
class ListRequest:
    search: str | None = None
    filters: dict[str, str] = field(default_factory=dict)
    ordering: str | None = None
    page: int = 1
    page_size: int = 0
    # unlimited asks for every matching row, which is what an export
    # wants. It overrides page/page_size rather than being page_size 0, so
    # "unset" and "all" stay distinguishable.
    unlimited: bool = False

    def window(self) -> tuple[int, int]:
        """The (offset, limit) pair a data source wants. A limit of 0 means no
        limit -- see `unlimited`.
        """
        if self.unlimited:
            return 0, 0
        size = self.page_size if self.page_size and self.page_size >= 1 else DEFAULT_PAGE_SIZE
        page = self.page if self.page and self.page >= 1 else 1
        return (page - 1) * size, size


class ListQuerier(Protocol):
    """An optional ModelAdmin capability: implement `list_page` to resolve search,
    filters, ordering and the page window in the data source itself, rather
    than in memory over everything get_queryset returns.

    All-or-nothing by design. The framework applies nothing further, because it
    cannot tell what the implementation already did and re-applying would
    double-filter. The returned total counts rows matching search+filters
    before the window. Not implementing it keeps the in-memory path.
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


def is_sortable(model_admin: Any, name: str) -> bool:
    """Whether a list column offers a sort. An unset sortable_by leaves every
    column sortable; an empty one leaves none."""
    sortable = model_admin.sortable_by
    return True if sortable is None else name in sortable


def links_to_record(model_admin: Any, name: str) -> bool:
    """Whether a list cell links to the record. An unset list_display_links
    links the first column, as Django does; an empty one links nothing and
    leaves the row menu as the way in."""
    linked = model_admin.list_display_links
    if linked is None:
        display = list(model_admin.list_display)
        return bool(display) and display[0] == name
    return name in linked


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


def apply_defaults(model_admin: Any, list_request: ListRequest) -> ListRequest:
    """Fill in the ModelAdmin's ordering and page size where the request named
    neither.

    Resolved before the query runs so a `list_page` implementation is told
    about them too: they are part of the question, not the answer. Idempotent,
    so a caller needing the resolved values can apply it once and pass the same
    request on.
    """
    changes = {}
    # A ?sort= naming a column the admin does not offer is dropped, so the
    # restriction holds for a hand-typed URL too. The default ordering below
    # is exempt: it is the admin's own choice, not user input.
    if list_request.ordering and not is_sortable(model_admin, list_request.ordering.lstrip("-")):
        list_request = replace(list_request, ordering=None)
    if not list_request.ordering:
        changes["ordering"] = model_admin.get_default_ordering()
    # Not for an unlimited request: that deliberately has no page.
    if not list_request.unlimited and list_request.page_size < 1:
        changes["page_size"] = model_admin.get_page_size()
    return replace(list_request, **changes) if changes else list_request


def list_objects(model_admin: Any, list_request: ListRequest) -> tuple[list[Any], int]:
    """Resolve a list query, and the only place that decides how: a ModelAdmin
    implementing `list_page` answers it itself, everything else loads the
    queryset and filters in memory.

    Every consumer goes through here -- list view, both exports, the
    autocomplete lookup, relation option lists -- so the paths cannot drift;
    the request's window is what separates "one page" from "capped at 20" from
    "every matching row". Returns the window's objects and the total before it.
    """
    list_request = apply_defaults(model_admin, list_request)
    if hasattr(model_admin, "list_page"):
        return model_admin.list_page(list_request)
    objects = execute_list_query(model_admin, model_admin.get_queryset(), list_request)
    total = len(objects)
    offset, limit = list_request.window()
    offset = min(offset, total)
    end = total if limit == 0 else min(offset + limit, total)
    return objects[offset:end], total


async def alist_objects(model_admin: Any, list_request: ListRequest) -> tuple[list[Any], int]:
    """Async counterpart of list_objects, for a ModelAdmin whose list_page or
    get_queryset is a coroutine function. It is what every request path uses --
    the list view, exports, the lookup route, relation option lists and inline
    child loading -- so async hooks work everywhere, on sync ModelAdmins too.
    """
    list_request = apply_defaults(model_admin, list_request)
    if hasattr(model_admin, "list_page"):
        return await maybe_await(model_admin.list_page(list_request))
    objects = execute_list_query(model_admin, await maybe_await(model_admin.get_queryset()), list_request)
    total = len(objects)
    offset, limit = list_request.window()
    offset = min(offset, total)
    end = total if limit == 0 else min(offset + limit, total)
    return objects[offset:end], total


# The reserved query parameter and form field carrying the list a page was
# reached from -- its search, filters, sort and page (docs/lists.md). It is
# what preserve_filters preserves: the pages reached from a list hand it
# back, so the trail out of a filtered list leads into it rather than into
# the bare one.
LIST_TOKEN_FIELD = "_list"


def safe_list_token(token: str | None, host: str, base_path: str) -> str:
    """Validate a token the way safe_redirect_path validates a Referer: same
    host, under the admin's base path. An invalid one yields "", which every
    caller reads as "no list to go back to"."""
    from polyadmin.core.csrf import safe_redirect_path

    if not token:
        return ""
    return safe_redirect_path(token, host, base_path, "") or ""


def with_list_token(url: str, token: str) -> str:
    """Append a validated token to a URL as the _list parameter, leaving the
    URL alone when there is none."""
    if not token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{LIST_TOKEN_FIELD}={quote(token, safe='')}"


# The panel's range form posts these three rather than one filter value,
# because a form cannot concatenate two inputs. Reserved names, in the
# same family as _list and _return.
RANGE_FOR_FIELD = "_range_for"
RANGE_FROM_FIELD = "_range_from"
RANGE_TO_FIELD = "_range_to"


def fold_range_params(
    model_admin: Any, filters: dict[str, str], range_for: str, from_value: str, to_value: str
) -> None:
    """Turn a range form's submission into the single filter value the
    grammar defines, in place. Folding here rather than in the browser is
    what keeps the range working with scripting off.

    `range_for` arrives from the client, so it is honoured only when the
    ModelAdmin actually declares a filter by that name -- otherwise a
    crafted form could inject any key into filters. Submitting both inputs
    empty clears the filter instead of setting an empty range.
    """
    if not range_for:
        return
    if not any(filt.name == range_for for filt in model_admin.filters):
        return
    if not from_value and not to_value:
        filters.pop(range_for, None)
        return
    filters[range_for] = f"{from_value}:{to_value}"
