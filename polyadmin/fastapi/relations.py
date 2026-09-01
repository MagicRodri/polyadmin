"""Relation-aware helpers for the FastAPI adapter."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.field import Field
from polyadmin.core.model_admin import ModelAdmin
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

        options = [
            (target_admin.get_pk(related), display_field.get_value(related))
            for related in target_admin.get_queryset()
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
