"""TemplateContext: the data handed to each rendered admin page.

One function per view type, all built on `base_context`, so every page gets the
same admin-wide data (nav, base path, flash messages) without repeating it.

Breadcrumbs are translated here, where they are built, in the request's
locale: the resource's name and the crumbs' own literals go through gettext,
an object's label is data and does not. Nav labels are left for the sidebar
template to translate, so each string is translated once.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from polyadmin.core.action import DELETE_SELECTED_NAME
from polyadmin.core.admin import Admin
from polyadmin.core.delete import (
    DELETE_PREVIEW_SAMPLE,
    ResolvedDeletePreview,
    previews_deletes,
)
from polyadmin.core.filter import (
    FILTER_KIND_DATE_RANGE,
    FILTER_KIND_RELATION,
    date_filter_range_values,
)
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.pagination import Page
from polyadmin.core.query import (
    LIST_TOKEN_FIELD,
    RANGE_FOR_FIELD,
    RANGE_FROM_FIELD,
    RANGE_TO_FIELD,
    ListRequest,
    is_sortable,
    links_to_record,
    with_list_token,
)
from polyadmin.i18n import gettext, ngettext


def default_permissions(model_admin: ModelAdmin) -> dict[str, bool]:
    """Permissions as if every capability the ModelAdmin declares is also
    authorized -- what you get with no Authorizer configured. Real per-
    principal permissions are computed by the adapter and passed in.
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
    """A short label for an object in a breadcrumb trail: the first search_fields
    entry (usually the most identifying), else the first list_display column,
    else the primary key.
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
    """One list-view URL, carrying over every parameter of the current request
    except those overridden (pass None to drop one).

    Every control on the list page is a link needing the same "keep what's
    there, change one thing" rule, so building it once here keeps the templates
    free of query-string assembly.
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


def _filter_form_hidden(list_request: ListRequest, exclude: str) -> list[dict[str, str]]:
    """Every list parameter except the one the form is about, as hidden
    fields. Without them, submitting the form would drop the reader's
    search, sort and other filters.
    """
    hidden = []
    if list_request.search:
        hidden.append({"name": "search", "value": list_request.search})
    if list_request.ordering:
        hidden.append({"name": "sort", "value": list_request.ordering})
    # Page is deliberately dropped: narrowing a list returns to page 1,
    # exactly as the choice links already do.
    for name in sorted(n for n in list_request.filters if n != exclude):
        hidden.append({"name": f"filter[{name}]", "value": list_request.filters[name]})
    return hidden


def _filter_controls(
    model_admin: ModelAdmin,
    list_request: ListRequest,
    base_path: str,
    relation_choices: dict[str, dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    """Per-filter choice lists with precomputed URLs. Each choice is a link, not a
    <select> option, preserving everything else and resetting to page 1.

    `relation_choices` carries what a relation filter cannot supply itself:
    the target's records, permission-filtered. It is computed by the
    adapter and passed in, because core must not import the adapter. A
    None entry means the principal may not view that target, and the
    filter is dropped rather than shown empty.
    """
    relation_choices = relation_choices or {}
    controls = []
    for filt in model_admin.filters:
        current = list_request.filters.get(filt.name, "")
        others = {n: v for n, v in list_request.filters.items() if n != filt.name}

        sourced: list[dict[str, str]] = []
        combobox = None
        if filt.control_kind == FILTER_KIND_RELATION:
            from_target = relation_choices.get(filt.name)
            if from_target is None:
                continue  # dropped, not emptied -- see relation_filter_choices
            sourced = from_target["choices"]
            combobox = from_target["combobox"]

        pairs = [
            *filt.choices_with_labels(),
            *((choice["value"], choice["label"]) for choice in sourced),
        ]
        choices = []
        for value, label in pairs:
            combined = {**others, filt.name: value} if value else others
            choices.append({
                "value": value,
                "label": label,
                "selected": value == current,
                "url": _list_url(model_admin, list_request, base_path, filters=combined),
            })
        range_from, range_to = "", ""
        if filt.control_kind == FILTER_KIND_DATE_RANGE:
            values = date_filter_range_values(current)
            if values is not None:
                range_from, range_to = values
        controls.append({
            "name": filt.name,
            "label": filt.label,
            "choices": choices,
            # The toolbar renders each filter as a dropdown trigger, so it
            # needs the active choice's label for the trigger itself and
            # a URL that clears just this filter.
            "active": next((c["label"] for c in choices if c["selected"] and c["value"]), None),
            "clear_url": _list_url(model_admin, list_request, base_path, filters=others),
            # This filter's raw value on this request. The badge counts on
            # it rather than on a selected choice: a custom date range and
            # a combobox selection are both real values that match no
            # declared choice, and counting choices treated those lists as
            # unfiltered.
            "current": current,
            # core.filter's control_kind as a plain string: "" for a link
            # list, "daterange" for the two date inputs, "relation" for
            # the combobox.
            "kind": filt.control_kind,
            # Prefilled into the range inputs when the current value is a
            # range rather than a preset. Both "" otherwise.
            "range_from": range_from,
            "range_to": range_to,
            # The GET form an input-bearing control submits: the list's own
            # path, plus every other parameter as a hidden field, so
            # submitting reproduces the list it was opened from with one
            # thing changed.
            "form_action": f"{base_path}/{model_admin.get_slug()}",
            "hidden": _filter_form_hidden(list_request, filt.name),
            # A relation filter whose field is in autocomplete_fields
            # renders the lookup-backed combobox instead of a link list --
            # the same declaration, and the same control, the form uses.
            "uses_combobox": combobox is not None,
            "lookup_url": (combobox or {}).get("lookup_url", ""),
            "selected_pk": (combobox or {}).get("selected_pk", ""),
            "selected_label": (combobox or {}).get("selected_label", ""),
        })
    return controls


def _filter_choice_url(
    model_admin: ModelAdmin, list_request: ListRequest, base_path: str, name: str, value: str
) -> str:
    """The list URL with one filter set to `value`, or cleared when it is
    empty -- every other parameter carried over."""
    filters = {other: v for other, v in list_request.filters.items() if other != name}
    if value:
        filters[name] = value
    return _list_url(model_admin, list_request, base_path, filters=filters)


def _sort_controls(model_admin: ModelAdmin, list_request: ListRequest, base_path: str) -> dict[str, Any]:
    """Per-column ascending/descending URLs and the current direction,
    for the sortable column-header dropdowns."""
    ordering = list_request.ordering or ""
    controls = {}
    for name in model_admin.list_display:
        direction = "asc" if ordering == name else ("desc" if ordering == f"-{name}" else None)
        controls[name] = {
            "direction": direction,
            # Outside sortable_by: the header renders as a plain label.
            "sortable": is_sortable(model_admin, name),
            "asc_url": _list_url(model_admin, list_request, base_path, ordering=name),
            "desc_url": _list_url(model_admin, list_request, base_path, ordering=f"-{name}"),
        }
    return controls


def _page_size_options(model_admin: ModelAdmin, list_request: ListRequest, base_path: str) -> list[dict[str, Any]]:
    """Rows-per-page choices. Changing the size returns to page 1: staying on page
    7 while quadrupling the size would land the reader somewhere they never
    asked to be.
    """
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


# GROUP_ICON is fixed, not per-category: a category is a string, not an
# object with settings of its own.
GROUP_ICON = "folder"


def build_nav(admin: Admin, base_path: str, active_key: str | None) -> list[dict[str, Any]]:
    """Ordered sidebar entries: flat links and category groups, interleaved in
    first-registration order. Entries the principal cannot view, and pages with
    show_in_nav=False, are omitted. A group's "active" flag defaults its
    accordion open and is true iff it holds the current page.
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
    """The category crumb, if any: the first segment after the home crumb, never a
    link and never active.
    """
    if not category:
        return []
    return [{"label": gettext(category), "url": None, "active": False}]


def _list_crumb_url(model_admin: ModelAdmin, base_path: str, list_token: str) -> str:
    """The breadcrumb back to the list: the one the page was reached from when
    preserve_filters handed us a token, the bare list otherwise. This is where
    a user actually returns, so it is the crumb that matters most."""
    return list_token or f"{base_path}/{model_admin.get_slug()}"


def base_context(
    admin: Admin,
    *,
    model_admin: ModelAdmin | None = None,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    breadcrumbs: list[dict[str, Any]] | None = None,
    active_nav_key: str | None = None,
    principal: Any = None,
    csrf_token: str = "",
    list_token: str = "",
) -> dict[str, Any]:
    if active_nav_key is None and model_admin is not None:
        active_nav_key = f"resource:{model_admin.get_slug()}"
    return {
        "admin": admin,
        # The list this page was reached from -- preserve_filters
        # (docs/lists.md). Forms post it back in a hidden field.
        "list_token": list_token,
        "model_admin": model_admin,
        "base_path": base_path,
        "messages": messages or [],
        "site_title": admin.site_title,
        "site_logo_url": admin.site_logo_url,
        "breadcrumbs": breadcrumbs or [],
        "nav_items": build_nav(admin, base_path, active_nav_key),
        # The sidebar footer shows who is signed in, so the principal has
        # to reach every page that renders a sidebar -- which is all of
        # them.
        "principal": principal,
        # Needed on every page: base.html renders it as a meta tag and
        # every no-JS form renders it as a hidden field.
        "csrf_token": csrf_token,
        # Whether there is a session to end. Without a login_backend the
        # admin has no logout route, so the control would be dead.
        "can_sign_out": admin.login_backend is not None,
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
    csrf_token: str = "",
    relation_filter_choices: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    list_request = list_request or ListRequest()
    # Carries search/filter/sort into the Export links so a download
    # matches what is on screen. page/page_size are excluded: an export is
    # of the whole filtered result.
    export_params: list[tuple[str, str]] = []
    if list_request.search:
        export_params.append(("search", list_request.search))
    for name, value in list_request.filters.items():
        export_params.append((f"filter[{name}]", value))
    if list_request.ordering:
        export_params.append(("sort", list_request.ordering))
    export_query = f"?{urlencode(export_params)}" if export_params else ""

    filter_controls = _filter_controls(
        model_admin, list_request, base_path, relation_filter_choices
    )

    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": gettext(model_admin.get_verbose_name()), "url": None, "active": True},
    ]

    return {
        **base_context(admin, principal=principal, csrf_token=csrf_token, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "page": page,
        "actions": _action_infos(model_admin),
        # A previewing resource has something to say before the delete, so
        # the row's Delete leads to the page that says it.
        "previews_deletes": previews_deletes(model_admin),
        # Which cells link to the record -- list_display_links.
        "linked_columns": [name for name in model_admin.list_display if links_to_record(model_admin, name)],
        # "?_list=<this list>" for the pages reached from here, so they lead
        # back into the list as it was left -- preserve_filters. Empty when
        # the ModelAdmin has it off.
        "list_query": (
            f"?{LIST_TOKEN_FIELD}={quote(_list_url(model_admin, list_request, base_path, page=list_request.page), safe='')}"
            if model_admin.preserve_filters
            else ""
        ),
        "list_display": list(model_admin.list_display),
        # "cells", not "values" -- the latter collides with dict.values,
        # the built-in method, when accessed via Jinja's dot notation.
        "rows": [
            {
                "pk": model_admin.get_pk(obj),
                "cells": model_admin.get_list_display_values(obj),
            }
            for obj in page.items
        ],
        "search": list_request.search or "",
        "filters": list_request.filters,
        "filter_controls": filter_controls,
        # The panel's range form field names, so the template never spells
        # a reserved parameter itself.
        "range_for_field": RANGE_FOR_FIELD,
        "range_from_field": RANGE_FROM_FIELD,
        "range_to_field": RANGE_TO_FIELD,
        "sort_controls": _sort_controls(model_admin, list_request, base_path),
        "page_size_options": _page_size_options(model_admin, list_request, base_path),
        # Precomputed for the same reason the filter links are: the
        # template should never assemble a query string.
        "page_urls": {
            "first": _list_url(model_admin, list_request, base_path, page=None),
            "previous": _list_url(model_admin, list_request, base_path, page=page.previous_page) if page.has_previous else None,
            "next": _list_url(model_admin, list_request, base_path, page=page.next_page) if page.has_next else None,
            "last": _list_url(model_admin, list_request, base_path, page=page.num_pages),
        },
        # Keeps sort and page size: those are how you are reading the
        # table, not what you are narrowing it to.
        "reset_url": _list_url(model_admin, list_request, base_path, search=None, filters=None, page=None),
        "has_active_filters": bool(list_request.search or list_request.filters),
        # Badges the Filters trigger, so the panel says how much it hides
        # without being opened. Search is excluded: it has its own visible
        # box.
        "active_filter_count": sum(1 for control in filter_controls if control["current"]),
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
    csrf_token: str = "",
    list_token: str = "",
) -> dict[str, Any]:
    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": gettext(model_admin.get_verbose_name()), "url": _list_crumb_url(model_admin, base_path, list_token)},
        {"label": _object_label(model_admin, obj), "url": None, "active": True},
    ]
    return {
        **base_context(admin, principal=principal, csrf_token=csrf_token, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs, list_token=list_token),
        "object": obj,
        "detail_fields": model_admin.get_detail_fields(),
        "actions": _action_infos(model_admin),
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
    csrf_token: str = "",
    list_token: str = "",
) -> dict[str, Any]:
    slug = model_admin.get_slug()
    if obj is not None:
        form_action = f"{base_path}/{slug}/{model_admin.get_pk(obj)}/edit"
    else:
        form_action = f"{base_path}/{slug}/create"

    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": gettext(model_admin.get_verbose_name()), "url": _list_crumb_url(model_admin, base_path, list_token)},
    ]
    if obj is not None:
        breadcrumbs.append({
            "label": _object_label(model_admin, obj),
            "url": with_list_token(f"{base_path}/{slug}/{model_admin.get_pk(obj)}", list_token),
        })
        breadcrumbs.append({"label": gettext("Edit"), "url": None, "active": True})
    else:
        breadcrumbs.append({"label": gettext("New"), "url": None, "active": True})

    return {
        **base_context(admin, principal=principal, csrf_token=csrf_token, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs, list_token=list_token),
        "object": obj,
        "data": data,
        "errors": errors or {},
        "non_field_errors": non_field_errors or [],
        "form_fields": model_admin.get_form_fields(),
        # Always at least one group (see ModelAdmin.get_fieldsets), so
        # the template has a single path for the declared and the
        # undeclared case.
        "fieldsets": model_admin.get_fieldsets(),
        "form_action": form_action,
        # save_as: only on an existing record, since there is nothing to copy
        # from on a create form.
        "allow_save_as": model_admin.save_as and obj is not None,
        # prepopulated_fields, for the behaviour in theme.html. Empty on an
        # edit form -- an existing record's slug is a real identifier, and
        # rewriting it from the title is how links rot.
        "prepopulated": (
            {
                target: {"from": list(sources), "unicode": target in model_admin.prepopulated_unicode}
                for target, sources in model_admin.prepopulated_fields.items()
            }
            if obj is None
            else {}
        ),
        "relation_options": relation_options or {},
        # The edit form offers Delete, so it needs the detail page's
        # permission map: otherwise the button renders for a principal the
        # route then rejects.
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
    csrf_token: str = "",
) -> dict[str, Any]:
    # A single active crumb -- since base.html has no separate <h1>,
    # this is the only page-title element the dashboard gets.
    breadcrumbs = [{"label": gettext(getattr(dashboard, "title", None) or "Dashboard"), "url": None, "active": True}]
    return {
        **base_context(admin, principal=principal, csrf_token=csrf_token, model_admin=None, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs),
        "dashboard": dashboard,
        "widgets": widgets,
    }


def delete_selected_context(
    admin: Admin,
    model_admin: ModelAdmin,
    selection: dict[str, Any],
    preview: Any,
    *,
    base_path: str = "/admin",
    principal: Any = None,
    csrf_token: str = "",
) -> dict[str, Any]:
    """The delete_selected confirmation page. `selection` carries objects,
    select_all, pks, list_request, fingerprint, return_to, changed, and the
    already permission-checked `items` (built by the adapter, since core must
    not import one)."""
    slug = model_admin.get_slug()
    objects = selection["objects"]
    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": gettext(model_admin.get_verbose_name()), "url": f"{base_path}/{slug}"},
        {"label": gettext("Delete"), "url": None, "active": True},
    ]
    heading = ngettext("Delete %(num)d record?", "Delete %(num)d records?", len(objects)) % {"num": len(objects)}
    return {
        **base_context(admin, principal=principal, csrf_token=csrf_token, model_admin=model_admin, base_path=base_path, breadcrumbs=breadcrumbs),
        "heading": heading,
        "items": selection["items"],
        "more": max(len(objects) - DELETE_PREVIEW_SAMPLE, 0),
        "selection": selection,
        "preview": delete_preview_view(preview, base_path),
    }


def _action_infos(model_admin: ModelAdmin) -> list[dict[str, Any]]:
    """The actions as the bulk bar and detail page see them. delete_selected on
    a ModelAdmin that previews deletes gets the server's confirmation page
    instead of the modal (docs/deletes.md)."""
    previews = previews_deletes(model_admin)
    infos = []
    for a in model_admin.get_actions():
        preview = previews and a.name == DELETE_SELECTED_NAME
        infos.append({"name": a.name, "label": a.label, "confirm": None if preview else a.confirm, "preview": preview})
    return infos


def delete_preview_view(preview: ResolvedDeletePreview | None, base_path: str) -> dict[str, Any]:
    """The delete preview as the templates see it (docs/deletes.md): headings
    translated, records labelled and linked, nothing the principal may not
    view named. None renders as an empty, unblocked preview."""
    preview = preview or ResolvedDeletePreview()

    def group(g):
        items = [
            {
                "label": _object_label(g.model_admin, obj),
                "url": f"{base_path}/{g.model_admin.get_slug()}/{g.model_admin.get_pk(obj)}",
            }
            for obj in g.visible
        ]
        items += [{"label": text, "url": None} for text in g.texts]
        heading = gettext("%(label)s (%(num)d)") % {"label": gettext(g.label), "num": g.total}
        return {"heading": heading, "items": items, "more": g.more, "hidden": g.hidden}

    return {
        "cascades": [group(g) for g in preview.cascades],
        "protected": [group(g) for g in preview.protected],
        "denied": ", ".join(gettext(label) for label in preview.denied_types),
        "blocked": preview.blocked,
    }


def delete_context(
    admin: Admin,
    model_admin: ModelAdmin,
    obj: Any,
    *,
    base_path: str = "/admin",
    messages: list[dict[str, Any]] | None = None,
    principal: Any = None,
    csrf_token: str = "",
    preview: ResolvedDeletePreview | None = None,
    list_token: str = "",
) -> dict[str, Any]:
    slug = model_admin.get_slug()
    breadcrumbs = [
        *category_breadcrumb(model_admin.category),
        {"label": gettext(model_admin.get_verbose_name()), "url": _list_crumb_url(model_admin, base_path, list_token)},
        {"label": _object_label(model_admin, obj), "url": with_list_token(f"{base_path}/{slug}/{model_admin.get_pk(obj)}", list_token)},
        {"label": gettext("Delete"), "url": None, "active": True},
    ]
    return {
        **base_context(admin, principal=principal, csrf_token=csrf_token, model_admin=model_admin, base_path=base_path, messages=messages, breadcrumbs=breadcrumbs, list_token=list_token),
        "object": obj,
        "object_label": _object_label(model_admin, obj),
        "preview": delete_preview_view(preview, base_path),
    }
