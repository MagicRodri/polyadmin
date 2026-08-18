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


def _filter_controls(model_admin: ModelAdmin, list_request: ListRequest, base_path: str) -> list[dict[str, Any]]:
    """Per-filter choice lists with precomputed URLs (Django-admin-style
    filter sidebar: each choice is a link, not a <select> option) --
    each link preserves search/ordering/other-filters and only changes
    the one filter it represents, resetting to page 1.
    """
    slug = model_admin.get_slug()
    controls = []
    for filt in model_admin.filters:
        current = list_request.filters.get(filt.name, "")
        choices = []
        for value, label in filt.choices_with_labels():
            params: list[tuple[str, str]] = []
            if list_request.search:
                params.append(("search", list_request.search))
            for name, other_value in list_request.filters.items():
                if name != filt.name:
                    params.append((f"filter[{name}]", other_value))
            if value:
                params.append((f"filter[{filt.name}]", value))
            if list_request.ordering:
                params.append(("sort", list_request.ordering))
            query = f"?{urlencode(params)}" if params else ""
            choices.append({"value": value, "label": label, "selected": value == current, "url": f"{base_path}/{slug}{query}"})
        controls.append({"name": filt.name, "label": filt.label, "choices": choices})
    return controls


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

    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": model_admin.get_verbose_name(), "url": None, "active": True},
    ]

    return {
        **base_context(admin, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
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
        "filter_controls": _filter_controls(model_admin, list_request, base_path),
        "ordering": list_request.ordering or "",
        "export_query": export_query,
        "permissions": permissions or default_permissions(model_admin),
        "relation_permissions": relation_permissions or {},
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
) -> dict[str, Any]:
    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": model_admin.get_verbose_name(), "url": f"{base_path}/{model_admin.get_slug()}"},
        {"label": _object_label(model_admin, obj), "url": None, "active": True},
    ]
    return {
        **base_context(admin, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
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
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
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
        **base_context(admin, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "object": obj,
        "data": data,
        "errors": errors or {},
        "non_field_errors": non_field_errors or [],
        "form_fields": list(model_admin.form_fields),
        "form_action": form_action,
        "relation_options": relation_options or {},
    }


def dashboard_context(
    admin: Admin,
    dashboard: Any,
    widgets: list[Any],
    *,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # A single active crumb -- since base.html has no separate <h1>,
    # this is the only page-title element the dashboard gets.
    breadcrumbs = [{"label": getattr(dashboard, "title", None) or "Dashboard", "url": None, "active": True}]
    return {
        **base_context(admin, model_admin=None, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
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
) -> dict[str, Any]:
    slug = model_admin.get_slug()
    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": model_admin.get_verbose_name(), "url": f"{base_path}/{slug}"},
        {"label": _object_label(model_admin, obj), "url": f"{base_path}/{slug}/{model_admin.get_pk(obj)}"},
        {"label": "Delete", "url": None, "active": True},
    ]
    return {
        **base_context(admin, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "object": obj,
    }
