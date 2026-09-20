"""Relation-aware helpers for the FastAPI adapter."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.field import Field
from polyadmin.core.filter import FILTER_KIND_RELATION
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.query import ListRequest, list_objects
from polyadmin.core.relation import Relation


def _relation_fields(
    model_admin: ModelAdmin, names: list[str]
) -> Iterator[tuple[str, Field, Relation]]:
    for name in names:
        field = model_admin.get_field(name)
        relation = getattr(field, "relation", None)
        if relation is not None:
            yield name, field, relation


def compute_relation_permissions(
    admin: Admin, principal: Any, model_admin: ModelAdmin, names: list[str]
) -> dict[str, bool]:
    """Whether the current principal may view each relation target
    referenced by `names` -- the admin must not link to an
    object the principal isn't authorized to see.
    """
    result: dict[str, bool] = {}
    for _, _, relation in _relation_fields(model_admin, names):
        if relation.target in result:
            continue
        try:
            target_admin = admin.get_model_admin(relation.target)
        except KeyError:
            result[relation.target] = False
            continue
        if not target_admin.can_view:
            result[relation.target] = False
        elif admin.authorizer is None:
            result[relation.target] = True
        else:
            result[relation.target] = admin.authorizer.can(
                principal, resource_permission(relation.target, "view"), target_admin
            )
    return result


def compute_relation_options(
    admin: Admin, model_admin: ModelAdmin, obj: Any = None
) -> dict[str, dict[str, Any]]:
    """Selectable options for each relation field in `model_admin.form_fields`.

    For a field listed in `model_admin.autocomplete_fields`, this skips
    loading the target's queryset entirely and only resolves the
    current selection's own label -- the rest of the options are
    fetched on demand from the /lookup route as the user
    types, via components/ui/field.html's combobox. Every other relation
    field keeps populating a same-page <select> from the target's full
    unfiltered queryset, gated only by its static `can_view` -- coarser
    than `compute_relation_permissions`, fine for a same-page selector.
    """
    autocomplete_names = set(model_admin.autocomplete_fields)
    result: dict[str, dict[str, Any]] = {}
    for name, field, relation in _relation_fields(
        model_admin, model_admin.get_form_fields()
    ):
        try:
            target_admin = admin.get_model_admin(relation.target)
        except KeyError:
            continue
        if not target_admin.can_view:
            continue
        display_field = target_admin.get_field(relation.display_field)
        current = field.get_value(obj) if obj is not None else None

        if name in autocomplete_names and field.field_type in (
            "foreignkey",
            "onetoone",
        ):
            selected_pk = target_admin.get_pk(current) if current is not None else None
            selected_label = (
                display_field.get_value(current) if current is not None else None
            )
            result[name] = {
                "options": [],
                "selected_pk": selected_pk,
                "selected_pks": [],
                "autocomplete": True,
                "selected_label": selected_label,
                "lookup_target": relation.target,
            }
            continue

        # unlimited: a non-autocomplete relation renders every choice
        # inline, which is exactly what this widget is for. Going through
        # list_objects means a list_page target answers this from its own
        # data source like every other list query.
        related_objects, _ = list_objects(target_admin, ListRequest(unlimited=True))
        options = [
            (target_admin.get_pk(related), display_field.get_value(related))
            for related in related_objects
        ]
        if field.field_type == "manytomany":
            selected_pks = [target_admin.get_pk(related) for related in (current or [])]
            result[name] = {
                "options": options,
                "selected_pk": None,
                "selected_pks": selected_pks,
                "autocomplete": False,
            }
        else:
            selected_pk = target_admin.get_pk(current) if current is not None else None
            result[name] = {
                "options": options,
                "selected_pk": selected_pk,
                "selected_pks": [],
                "autocomplete": False,
            }
    return result


def relation_filter_choices(
    admin: Admin, principal: Any, model_admin: ModelAdmin, field: Any
) -> list[dict[str, str]] | None:
    """A relation filter's choice list: every record of the target
    ModelAdmin, as {"value", "label"} pairs.

    None when the principal may not view the target. The caller drops the
    filter entirely in that case -- an empty filter group reads as a
    broken control, and a reader who may not see organizations should not
    be told they exist. This is the principal-aware check, not
    compute_relation_options' coarser can_view: a filter offers records by
    name, so it has to answer to the same authorizer the target's own list
    does.

    The queryset is loaded whole and uncapped, exactly as
    compute_relation_options already does for a non-autocomplete relation
    <select>. autocomplete_fields is the answer to a large target, and it
    is the same answer in both places; a cap here and not there would have
    the panel and the form disagree about the same relation.
    """
    relation = getattr(field, "relation", None)
    if relation is None:
        return None
    allowed = compute_relation_permissions(admin, principal, model_admin, [field.name])
    if not allowed.get(relation.target, False):
        return None
    target_admin = admin.get_model_admin(relation.target)
    if target_admin is None:
        return None
    related_objects, _ = list_objects(target_admin, ListRequest(unlimited=True))
    try:
        display_field = target_admin.get_field(relation.display_field)
    except KeyError:
        display_field = None
    choices = []
    for related in related_objects:
        pk = str(target_admin.get_pk(related))
        label = str(display_field.get_value(related)) if display_field is not None else pk
        choices.append({"value": pk, "label": label})
    return choices


def relation_filter_choices_for(
    admin: Admin,
    principal: Any,
    model_admin: ModelAdmin,
    filters: dict[str, str] | None = None,
    base_path: str = "/admin",
) -> dict[str, dict[str, Any] | None]:
    """What each relation-kind filter needs but cannot supply itself,
    keyed by filter name. A None value means "the principal may not view
    this target, drop the filter".

    Each entry is {"choices": [...], "combobox": {...} | None}: a relation
    in `autocomplete_fields` gets the combobox and no choices, because the
    point of that declaration is never loading the target's queryset into
    the page; every other relation gets the link list.

    Computed here and passed into `list_context` rather than resolved
    inside it: core must not import the adapter (core/page.py), and this
    needs the adapter's relation-permission check. That is the same
    arrangement `delete_selected_context` already uses for its
    permission-checked item list.
    """
    filters = filters or {}
    sourced: dict[str, dict[str, Any] | None] = {}
    for filt in model_admin.filters:
        if filt.control_kind != FILTER_KIND_RELATION:
            continue
        try:
            field = model_admin.get_field(filt.name)
        except KeyError:
            sourced[filt.name] = None
            continue
        if filt.name in model_admin.autocomplete_fields:
            if not relation_filter_target_is_viewable(admin, principal, model_admin, field):
                sourced[filt.name] = None
                continue
            sourced[filt.name] = {
                "choices": [],
                "combobox": relation_filter_combobox(
                    admin, principal, model_admin, field, filters.get(filt.name, ""), base_path
                ),
            }
            continue
        choices = relation_filter_choices(admin, principal, model_admin, field)
        sourced[filt.name] = None if choices is None else {"choices": choices, "combobox": None}
    return sourced


def relation_filter_target_is_viewable(
    admin: Admin, principal: Any, model_admin: ModelAdmin, field: Any
) -> bool:
    """Whether the principal may view a relation filter's target, without
    loading any of it. The combobox path needs the permission answer but
    not the records.
    """
    relation = getattr(field, "relation", None)
    if relation is None:
        return False
    allowed = compute_relation_permissions(admin, principal, model_admin, [field.name])
    return allowed.get(relation.target, False)


def relation_filter_combobox(
    admin: Admin, principal: Any, model_admin: ModelAdmin, field: Any, current: str, base_path: str
) -> dict[str, str]:
    """What the panel's combobox needs for a relation filter: the target's
    lookup route, and the label of whatever is currently selected. It
    loads no queryset -- that is the whole point of autocomplete_fields.

    `current` is the filter's raw value, which is the target's primary key.
    """
    relation = field.relation
    result = {
        "lookup_url": f"{base_path}/{relation.target}/lookup",
        "selected_pk": "",
        "selected_label": "",
    }
    if not current:
        return result
    target_admin = admin.get_model_admin(relation.target)
    if target_admin is None:
        return result
    # One object, not the queryset: the trigger has to show what is
    # selected or the reader cannot tell what they are filtering by.
    related = target_admin.get_object(current)
    if related is None:
        return result
    result["selected_pk"] = current
    try:
        display_field = target_admin.get_field(relation.display_field)
        result["selected_label"] = str(display_field.get_value(related))
    except KeyError:
        result["selected_label"] = current
    return result
