"""Inline-aware helpers for the FastAPI adapter -- builds the render
context for a ModelAdmin's declared `inlines` (see core/inline.py) and
validates those declarations at router-mount time.
"""
from __future__ import annotations

from typing import Any

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.inline import Inline, filter_inline_children
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.fastapi.auth import compute_permissions
from polyadmin.fastapi.relations import compute_relation_options


def inline_label(admin: Admin, inline: Inline) -> str:
    child_admin = admin.get_model_admin(inline.child)
    return inline.label or f"{child_admin.get_verbose_name()}s"


def validate_inlines(admin: Admin, model_admin: ModelAdmin) -> None:
    """The two startup invariants an `Inline` declaration must satisfy
    -- run once per registered ModelAdmin at router-mount time (after
    every ModelAdmin is registered, so cross-admin lookups resolve),
    before any request is served. Mirrors Admin.register's
    fail-fast-on-duplicate-slug precedent.
    """
    parent_slug = model_admin.get_slug()
    seen: set[str] = set()
    for inline in model_admin.inlines:
        if inline.child in seen:
            raise ValueError(f"{parent_slug!r} declares more than one inline for child {inline.child!r}.")
        seen.add(inline.child)

        try:
            child_admin = admin.get_model_admin(inline.child)
        except KeyError:
            raise ValueError(f"{parent_slug!r}'s inline references unknown child {inline.child!r}.") from None

        try:
            field = child_admin.get_field(inline.fk_field)
        except KeyError:
            field = None
        relation = getattr(field, "relation", None) if field is not None else None
        if (
            field is None
            or relation is None
            or field.field_type not in ("foreignkey", "onetoone")
            or relation.target != parent_slug
        ):
            raise ValueError(
                f"{parent_slug!r}'s inline fk_field {inline.fk_field!r} on child {inline.child!r} must be "
                f"a ForeignKeyField/OneToOneField whose relation targets {parent_slug!r}."
            )


def build_inline_context(
    admin: Admin,
    principal: Any,
    model_admin: ModelAdmin,
    obj: Any | None,
    mode: str,
    base_path: str,
    *,
    redisplay: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One entry per `model_admin.inlines` the current principal may
    view at all -- an entry is omitted entirely (the whole section
    hidden, not just its controls) if the principal lacks the child's
    own `.view` permission, same principle as relation-link hiding
    elsewhere in the framework.

    `mode` is "placeholder" (create page -- no parent pk yet, no rows
    or add-form built), "edit" (rows + a persistent blank add-row, all
    editable), or "readonly" (rows only, using the child's
    detail_fields, no add/edit/remove controls).

    `redisplay`, when given, is `{"pk": child_pk_or_None, "data":...,
    "errors":...}` for the one row (or the add-row, if pk is None)
    being redisplayed after a failed inline mutation.
    """
    sections: list[dict[str, Any]] = []
    for inline in model_admin.inlines:
        try:
            child_admin = admin.get_model_admin(inline.child)
        except KeyError:
            continue
        if not child_admin.can_view:
            continue
        if admin.authorizer is not None and not admin.authorizer.can(
            principal, resource_permission(inline.child, "view"), child_admin
        ):
            continue

        child_perms = compute_permissions(admin, principal, child_admin)
        field_names = [name for name in child_admin.form_fields if name != inline.fk_field]
        detail_field_names = [name for name in child_admin.get_detail_fields() if name != inline.fk_field]

        rows: list[dict[str, Any]] = []
        add_row: dict[str, Any] | None = None
        if mode != "placeholder":
            parent_pk = model_admin.get_pk(obj)
            children = filter_inline_children(child_admin, inline.fk_field, model_admin, parent_pk)
            for child_obj in children:
                child_pk = child_admin.get_pk(child_obj)
                row_redisplay = (
                    redisplay
                    if redisplay is not None and redisplay.get("pk") is not None and str(redisplay["pk"]) == str(child_pk)
                    else None
                )
                rows.append(
                    {
                        "pk": child_pk,
                        "obj": child_obj,
                        "data": row_redisplay["data"] if row_redisplay else None,
                        "errors": row_redisplay["errors"] if row_redisplay else {},
                        "relation_options": compute_relation_options(admin, child_admin, obj=child_obj)
                        if mode == "edit"
                        else {},
                        "update_url": f"{base_path}/{model_admin.get_slug()}/{parent_pk}/inlines/{inline.child}/{child_pk}",
                        "delete_url": f"{base_path}/{model_admin.get_slug()}/{parent_pk}/inlines/{inline.child}/{child_pk}",
                        "detail_url": f"{base_path}/{inline.child}/{child_pk}",
                    }
                )
            if mode == "edit" and child_perms["can_create"]:
                add_redisplay = redisplay if redisplay is not None and redisplay.get("pk") is None else None
                add_row = {
                    "data": add_redisplay["data"] if add_redisplay else None,
                    "errors": add_redisplay["errors"] if add_redisplay else {},
                    "relation_options": compute_relation_options(admin, child_admin),
                    "create_url": f"{base_path}/{model_admin.get_slug()}/{parent_pk}/inlines/{inline.child}",
                }

        sections.append(
            {
                "slug": inline.child,
                "label": inline_label(admin, inline),
                "layout": inline.layout,
                "mode": mode,
                "child_admin": child_admin,
                "field_names": field_names,
                "detail_field_names": detail_field_names,
                "can_change": child_perms["can_update"],
                "can_delete": child_perms["can_delete"],
                "rows": rows,
                "add_row": add_row,
            }
        )
    return sections
