"""TemplateContext: the data handed to each rendered admin page.

One function per view type, all built on top of `base_context` so every
page gets the same admin-wide data (nav, base path, flash messages)
without repeating it.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from polyadmin.core.admin import Admin
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.pagination import Page
from polyadmin.core.query import ListRequest


def default_permissions(model_admin: ModelAdmin) -> dict[str, bool]:
    """Permissions as if every capability the ModelAdmin declares is
    also authorized -- what you get with no Authorizer configured.
    Real per-principal permissions are computed by the adapter
    and passed in instead.
    """
    # Keys are "can_view" etc, not "view"/"update" -- "update" in
    # particular would collide with the dict.update method when
    # accessed via Jinja's dot notation (permissions.update).
    return {
        "can_view": model_admin.can_view,
        "can_create": model_admin.can_create,
        "can_update": model_admin.can_update,
        "can_delete": model_admin.can_delete,
        "can_export": model_admin.can_export,
    }


def _object_label(model_admin: ModelAdmin, obj: Any) -> str:
    """A short human-readable label for an object in a breadcrumb trail.
    Prefers the first search_fields entry (usually the most identifying
    field, e.g. "email") over the first list_display column (often the
    primary key), falling back to the primary key itself.
    """
    display_fields = list(model_admin.search_fields) or list(model_admin.list_display) or model_admin.get_detail_fields()
    if display_fields:
        field = model_admin.get_field(display_fields[0])
        return str(field.get_value(obj))
    return str(model_admin.get_pk(obj))


# Choices offered by the list view's "Rows per page" control. 25 is the
# handler default, so it's the one size a URL never has to spell out.
PAGE_SIZE_CHOICES = (10, 25, 50, 100)
DEFAULT_PAGE_SIZE = 25

_KEEP = object()


def _list_url(
    model_admin: ModelAdmin,
    list_request: ListRequest,
    base_path: str,
    *,
    search: Any = _KEEP,
    filters: Any = _KEEP,
    ordering: Any = _KEEP,
    page: int | None = None,
    page_size: Any = _KEEP,
) -> str:
    """One list-view URL, with every parameter carried over from the
    current request except the ones explicitly overridden.

    Every control on the list page (filters, sort, paging, rows-per-page,
    reset) is a link, so they all need the same "keep what's there,
    change one thing" rule. Building it once here is what keeps the
    templates free of query-string assembly -- pass `None` for a
    parameter to drop it rather than keep it.
    """
    search = list_request.search if search is _KEEP else search
    filters = list_request.filters if filters is _KEEP else filters
    ordering = list_request.ordering if ordering is _KEEP else ordering
    page_size = list_request.page_size if page_size is _KEEP else page_size

    params: list[tuple[str, str]] = []
    if search:
        params.append(("search", search))
    for name, value in (filters or {}).items():
        params.append((f"filter[{name}]", value))
    if ordering:
        params.append(("sort", ordering))
    # page 1 and the default size are the implied state; leaving them out
    # keeps the common URL clean and makes "reset" a bare path.
    if page and page > 1:
        params.append(("page", str(page)))
    if page_size and page_size != DEFAULT_PAGE_SIZE:
        params.append(("page_size", str(page_size)))
    query = f"?{urlencode(params)}" if params else ""
    return f"{base_path}/{model_admin.get_slug()}{query}"


def _filter_controls(model_admin: ModelAdmin, list_request: ListRequest, base_path: str) -> list[dict[str, Any]]:
    """Per-filter choice lists with precomputed URLs -- each choice is a
    link (not a <select> option) that preserves search/ordering/
    other-filters and only changes the one filter it represents,
    resetting to page 1.
    """
    controls = []
    for filt in model_admin.filters:
        current = list_request.filters.get(filt.name, "")
        others = {n: v for n, v in list_request.filters.items() if n != filt.name}
        choices = []
        for value, label in filt.choices_with_labels():
            combined = {**others, filt.name: value} if value else others
            choices.append({
                "value": value,
                "label": label,
                "selected": value == current,
                "url": _list_url(model_admin, list_request, base_path, filters=combined),
            })
        controls.append({
            "name": filt.name,
            "label": filt.label,
            "choices": choices,
            # The toolbar renders each filter as a dropdown trigger, so it
            # needs the active choice's label for the trigger itself and
            # a URL that clears just this filter.
            "active": next((c["label"] for c in choices if c["selected"] and c["value"]), None),
            "clear_url": _list_url(model_admin, list_request, base_path, filters=others),
        })
    return controls


def _sort_controls(model_admin: ModelAdmin, list_request: ListRequest, base_path: str) -> dict[str, Any]:
    """Per-column ascending/descending URLs and the current direction,
    for the sortable column-header dropdowns."""
    ordering = list_request.ordering or ""
    controls = {}
    for name in model_admin.list_display:
        direction = "asc" if ordering == name else ("desc" if ordering == f"-{name}" else None)
        controls[name] = {
            "direction": direction,
            "asc_url": _list_url(model_admin, list_request, base_path, ordering=name),
            "desc_url": _list_url(model_admin, list_request, base_path, ordering=f"-{name}"),
        }
    return controls


def _page_size_options(model_admin: ModelAdmin, list_request: ListRequest, base_path: str) -> list[dict[str, Any]]:
    """Rows-per-page choices. Changing the size returns to page 1 --
    staying on page 7 while quadrupling the page size would land the
    reader somewhere they never asked to be."""
    return [
        {
            "size": size,
            "selected": size == list_request.page_size,
            "url": _list_url(model_admin, list_request, base_path, page=None, page_size=size),
        }
        for size in PAGE_SIZE_CHOICES
    ]


def _nav_link(key: str, label: str, url: str, icon: str, active_key: str | None) -> dict[str, Any]:
    return {"type": "link", "key": key, "label": label, "url": url, "icon": icon, "active": key == active_key}


# GROUP_ICON is fixed, not configurable per category -- a category is
# just a string, not an object with its own settings -- so every
# accordion section uses the same icon, distinct from any resource's
# own icon (which nested links keep showing, see build_nav).
GROUP_ICON = "folder"


def build_nav(admin: Admin, base_path: str, active_key: str | None) -> list[dict[str, Any]]:
    """Ordered sidebar entries: flat links and category-grouped
    accordion sections, interleaved in first-registration-appearance
    order across ModelAdmins and AdminPages. ModelAdmins with
    can_view=False and AdminPages with show_in_nav=False are omitted.
    A group's own "active" flag (used to default its accordion open)
    is true iff any of its links is the current page.
    """
    order: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}

    def add(link: dict[str, Any], category: str | None) -> None:
        if category is None:
            order.append(link)
            return
        group = groups.get(category)
        if group is None:
            group = {"type": "group", "label": category, "icon": GROUP_ICON, "links": []}
            groups[category] = group
            order.append(group)
        group["links"].append(link)

    for ma in admin.model_admins:
        if ma.can_view:
            key = f"resource:{ma.get_slug()}"
            add(
                _nav_link(key, ma.get_verbose_name(), f"{base_path}/{ma.get_slug()}", ma.icon, active_key),
                ma.category,
            )
    for page in admin.pages:
        if page.show_in_nav:
            key = f"page:{page.path}"
            add(_nav_link(key, page.label, f"{base_path}{page.path}", page.icon, active_key), page.category)

    for entry in order:
        if entry["type"] == "group":
            entry["active"] = any(link["active"] for link in entry["links"])
    return order


def category_breadcrumb(category: str | None) -> list[dict[str, Any]]:
    """The category crumb, if any -- always the first segment after
    the implicit home crumb, never a link (there's no route for a
    category by itself) and never the *active*/current-page crumb.
    """
    if not category:
        return []
    return [{"label": category, "url": None, "active": False}]


def base_context(
    admin: Admin,
    *,
    model_admin: ModelAdmin | None = None,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    breadcrumbs: list[dict[str, Any]] | None = None,
    active_nav_key: str | None = None,
    principal: Any = None,
) -> dict[str, Any]:
    if active_nav_key is None and model_admin is not None:
        active_nav_key = f"resource:{model_admin.get_slug()}"
    return {
        "admin": admin,
        "model_admin": model_admin,
        "base_path": base_path,
        "messages": messages or [],
        "site_title": admin.site_title,
        "site_logo_url": admin.site_logo_url,
        "breadcrumbs": breadcrumbs or [],
        "nav_items": build_nav(admin, base_path, active_nav_key),
        # The sidebar's footer (shadcn sidebar-07's NavUser) shows who
        # is signed in, so the principal has to reach every page that
        # renders a sidebar -- which is all of them.
        "principal": principal,
    }


def list_context(
    admin: Admin,
    model_admin: ModelAdmin,
    page: Page,
    *,
    list_request: ListRequest | None = None,
    permissions: dict[str, bool] | None = None,
    relation_permissions: dict[str, bool] | None = None,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    principal: Any = None,
) -> dict[str, Any]:
    list_request = list_request or ListRequest()
    # Carries the current search/filter/sort into the Export links, so
    # exporting always downloads the same filtered dataset shown on
    # screen -- deliberately excludes page/page_size, since
    # export is of the whole filtered result, not just the current page.
    export_params: list[tuple[str, str]] = []
    if list_request.search:
        export_params.append(("search", list_request.search))
    for name, value in list_request.filters.items():
        export_params.append((f"filter[{name}]", value))
    if list_request.ordering:
        export_params.append(("sort", list_request.ordering))
    export_query = f"?{urlencode(export_params)}" if export_params else ""

    filter_controls = _filter_controls(model_admin, list_request, base_path)

    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": model_admin.get_verbose_name(), "url": None, "active": True},
    ]

    return {
        **base_context(admin, principal=principal, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "page": page,
        "actions": [{"name": a.name, "label": a.label, "confirm": a.confirm} for a in model_admin.actions],
        "list_display": list(model_admin.list_display),
        # "cells", not "values" -- the latter collides with dict.values,
        # the built-in method, when accessed via Jinja's dot notation.
        "rows": [
            {"pk": model_admin.get_pk(obj), "cells": model_admin.get_list_display_values(obj)}
            for obj in page.items
        ],
        "search": list_request.search or "",
        "filters": list_request.filters,
        "filter_controls": filter_controls,
        "sort_controls": _sort_controls(model_admin, list_request, base_path),
        "page_size_options": _page_size_options(model_admin, list_request, base_path),
        # Every paging control is a precomputed URL for the same reason
        # the filter links are: the template should never assemble a
        # query string. First/last exist because the tasks-style footer
        # offers all four jumps, not just prev/next.
        "page_urls": {
            "first": _list_url(model_admin, list_request, base_path, page=None),
            "previous": _list_url(model_admin, list_request, base_path, page=page.previous_page) if page.has_previous else None,
            "next": _list_url(model_admin, list_request, base_path, page=page.next_page) if page.has_next else None,
            "last": _list_url(model_admin, list_request, base_path, page=page.num_pages),
        },
        # Clears search and every filter but deliberately keeps sort and
        # page size: those are how you're reading the table, not what
        # you're narrowing it to.
        "reset_url": _list_url(model_admin, list_request, base_path, search=None, filters=None, page=None),
        "has_active_filters": bool(list_request.search or list_request.filters),
        # How many declared filters are currently narrowing the list --
        # the badge on the Filters trigger, so the panel says how much
        # it's hiding without being opened. Search isn't included, since
        # it has its own visible box in the toolbar. Mirrors
        # go-polyadmin's listData.ActiveFilterCount.
        "active_filter_count": sum(1 for control in filter_controls if control["active"]),
        "ordering": list_request.ordering or "",
        "export_query": export_query,
        "permissions": permissions or default_permissions(model_admin),
        "relation_permissions": relation_permissions or {},
        "reorderable": model_admin.enable_reordering,
    }


def detail_context(
    admin: Admin,
    model_admin: ModelAdmin,
    obj: Any,
    *,
    permissions: dict[str, bool] | None = None,
    relation_permissions: dict[str, bool] | None = None,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    principal: Any = None,
) -> dict[str, Any]:
    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": model_admin.get_verbose_name(), "url": f"{base_path}/{model_admin.get_slug()}"},
        {"label": _object_label(model_admin, obj), "url": None, "active": True},
    ]
    return {
        **base_context(admin, principal=principal, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "object": obj,
        "detail_fields": model_admin.get_detail_fields(),
        "actions": [{"name": a.name, "label": a.label, "confirm": a.confirm} for a in model_admin.actions],
        "permissions": permissions or default_permissions(model_admin),
        "relation_permissions": relation_permissions or {},
    }


def form_context(
    admin: Admin,
    model_admin: ModelAdmin,
    *,
    obj: Any | None = None,
    data: dict[str, Any] | None = None,
    errors: dict[str, list[str]] | None = None,
    non_field_errors: list[str] | None = None,
    relation_options: dict[str, list[tuple[Any, Any]]] | None = None,
    permissions: dict[str, bool] | None = None,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    principal: Any = None,
) -> dict[str, Any]:
    slug = model_admin.get_slug()
    if obj is not None:
        form_action = f"{base_path}/{slug}/{model_admin.get_pk(obj)}/edit"
    else:
        form_action = f"{base_path}/{slug}/create"

    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": model_admin.get_verbose_name(), "url": f"{base_path}/{slug}"},
    ]
    if obj is not None:
        breadcrumbs.append({"label": _object_label(model_admin, obj), "url": f"{base_path}/{slug}/{model_admin.get_pk(obj)}"})
        breadcrumbs.append({"label": "Edit", "url": None, "active": True})
    else:
        breadcrumbs.append({"label": "New", "url": None, "active": True})

    return {
        **base_context(admin, principal=principal, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "object": obj,
        "data": data,
        "errors": errors or {},
        "non_field_errors": non_field_errors or [],
        "form_fields": list(model_admin.form_fields),
        "form_action": form_action,
        "relation_options": relation_options or {},
        # The edit form offers Delete in its action bar, so it needs the
        # same permission map the detail page gets -- otherwise the
        # button would render for a principal the authorizer would then
        # reject at the route.
        "permissions": permissions or default_permissions(model_admin),
    }


def dashboard_context(
    admin: Admin,
    dashboard: Any,
    widgets: list[Any],
    *,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    principal: Any = None,
) -> dict[str, Any]:
    # A single active crumb -- since base.html has no separate <h1>,
    # this is the only page-title element the dashboard gets.
    breadcrumbs = [{"label": getattr(dashboard, "title", None) or "Dashboard", "url": None, "active": True}]
    return {
        **base_context(admin, principal=principal, model_admin=None, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "dashboard": dashboard,
        "widgets": widgets,
    }


def delete_context(
    admin: Admin,
    model_admin: ModelAdmin,
    obj: Any,
    *,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    principal: Any = None,
) -> dict[str, Any]:
    slug = model_admin.get_slug()
    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": model_admin.get_verbose_name(), "url": f"{base_path}/{slug}"},
        {"label": _object_label(model_admin, obj), "url": f"{base_path}/{slug}/{model_admin.get_pk(obj)}"},
        {"label": "Delete", "url": None, "active": True},
    ]
    return {
        **base_context(admin, principal=principal, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "object": obj,
    }
