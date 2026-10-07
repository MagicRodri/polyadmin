"""The page between choosing a form action and running it (docs/model-admin.md).

It reuses delete_selected's selection plumbing -- hidden pks or select-all
filters, _return, _fingerprint, _confirmed -- so a form action works from the
list's bulk bar and a record's detail page alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from polyadmin.core._async import maybe_await
from polyadmin.core.action import BULK_EDIT_NAME, Action
from polyadmin.core.authorization import resource_permission
from polyadmin.core.delete import selection_fingerprint
from polyadmin.core.query import ListRequest, alist_objects
from polyadmin.core.template_context import _object_label
from polyadmin.contrib.fastapi.auth import authorize_object
from polyadmin.contrib.fastapi.deletes import CONFIRMED_FIELD, FINGERPRINT_FIELD, selection_items
from polyadmin.i18n import gettext

CHANGE_PREFIX = "_change_"
_SINGLE = ("foreignkey", "onetoone")


@dataclass
class ActionFormRequest:
    request: Request
    form: Any
    admin: Any
    model_admin: Any
    renderer: Any
    principal: Any
    action: Action
    objects: list[Any]
    select_all: bool
    return_to: str
    list_request: Any
    base_path: str
    # The rows a bulk edit's user ticked "Change" on.
    ticked: set[str] = dc_field(default_factory=set)


def _default_data(fields: list[Any]) -> dict[str, Any]:
    return {f.name: f.default for f in fields if f.has_default}


def parse_action_form(form: Any, fields: list[Any], only: set[str] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in fields:
        if only is not None and field.name not in only:
            continue
        if field.field_type == "boolean":
            data[field.name] = field.name in form
        elif field.field_type == "manytomany":
            data[field.name] = form.getlist(field.name)
        else:
            data[field.name] = field.parse_form_value(form.get(field.name))
    return data


def validate_action_form(fields: list[Any], data: dict[str, Any]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for field in fields:
        if field.name in data and (field_errors := field.validate(data[field.name])):
            errors[field.name] = field_errors
    return errors


def _autocomplete_names(admin: Any, model_admin: Any, action: Action) -> set[str]:
    """Which relation fields render as the lookup combobox. Bulk edit follows
    the ModelAdmin's own edit form; any other action's single-valued relation
    does whenever its target can be searched."""
    if action.name == BULK_EDIT_NAME:
        return set(model_admin.autocomplete_fields)
    names = set()
    for field in action.form or ():
        relation = getattr(field, "relation", None)
        if relation is None or field.field_type not in _SINGLE:
            continue
        try:
            target = admin.get_model_admin(relation.target)
        except KeyError:
            continue
        if target.search_fields:
            names.add(field.name)
    return names


def _pk(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


async def action_relation_options(
    admin: Any, principal: Any, fields: list[Any], data: dict[str, Any], autocomplete: set[str]
) -> dict[str, dict[str, Any]]:
    """Like compute_relation_options, but for fields that belong to no record:
    the current value is a posted pk, not a related object. Pks are compared
    as strings, since the posted one is a string and get_pk's may not be.

    Gated on the principal's `{target}.view`, the check the target's /lookup
    makes: an action may need no more than the resource's own `.view`, so the
    coarser `can_view` the edit form relies on would name records the
    principal may not see."""
    result: dict[str, dict[str, Any]] = {}
    for field in fields:
        relation = getattr(field, "relation", None)
        if relation is None:
            continue
        try:
            target_admin = admin.get_model_admin(relation.target)
        except KeyError:
            continue
        if not target_admin.can_view or (
            admin.authorizer is not None
            and not admin.authorizer.can(principal, resource_permission(relation.target, "view"), target_admin)
        ):
            continue
        display_field = target_admin.get_field(relation.display_field)
        value = data.get(field.name)
        if field.name in autocomplete and field.field_type in _SINGLE:
            selected = _pk(value)
            label = None
            if selected is not None:
                current = await maybe_await(target_admin.get_object(selected))
                label = display_field.get_value(current) if current is not None else None
            result[field.name] = {
                "options": [],
                "selected_pk": selected,
                "selected_pks": [],
                "autocomplete": True,
                "selected_label": label,
                "lookup_target": relation.target,
            }
            continue
        related, _ = await alist_objects(target_admin, ListRequest(unlimited=True))
        options = [(str(target_admin.get_pk(r)), display_field.get_value(r)) for r in related]
        many = field.field_type == "manytomany"
        result[field.name] = {
            "options": options,
            "selected_pk": None if many else _pk(value),
            "selected_pks": [str(v) for v in (value or [])] if many else [],
            "autocomplete": False,
        }
    return result


def bulk_edit_blocked(admin: Any, principal: Any, model_admin: Any, objects: list[Any], names: set[str]) -> list[str]:
    """Labels of the records the principal may not update, or on which one of
    `names` is read-only. Any at all blocks the whole edit."""
    permission = resource_permission(model_admin.get_slug(), "update")
    return [
        _object_label(model_admin, obj)
        for obj in objects
        if not authorize_object(admin, principal, permission, obj)
        or any(model_admin.is_readonly(name, obj) for name in names)
    ]


async def render_action_form_page(
    ctx: ActionFormRequest,
    data: dict[str, Any],
    errors: dict[str, list[str]],
    *,
    changed: bool = False,
    blocked: list[str] | tuple[str, ...] = (),
    status_code: int = 200,
) -> HTMLResponse:
    model_admin = ctx.model_admin
    fields = list(ctx.action.form or ())
    selection = {
        "objects": ctx.objects,
        "select_all": ctx.select_all,
        "pks": [] if ctx.select_all else [str(model_admin.get_pk(obj)) for obj in ctx.objects],
        "list_request": ctx.list_request,
        "fingerprint": selection_fingerprint(model_admin, ctx.objects),
        "return_to": ctx.return_to,
        "changed": changed,
        "items": selection_items(ctx.admin, ctx.principal, model_admin, ctx.objects, ctx.base_path),
    }
    relation_options = await action_relation_options(
        ctx.admin, ctx.principal, fields, data, _autocomplete_names(ctx.admin, model_admin, ctx.action)
    )
    html = ctx.renderer.render_action_form(
        ctx.admin,
        model_admin,
        ctx.action,
        selection,
        fields=fields,
        data=data,
        errors=errors,
        relation_options=relation_options,
        ticked=ctx.ticked,
        blocked=list(blocked),
        base_path=ctx.base_path,
        principal=ctx.principal,
        csrf_token=ctx.request.state.csrf_token,
    )
    return HTMLResponse(html, status_code=status_code)


async def resolve_action_form(ctx: ActionFormRequest) -> HTMLResponse | dict[str, Any]:
    """The page to answer with, or the validated data to run the action with."""
    fields = list(ctx.action.form or ())
    if not ctx.form.get(CONFIRMED_FIELD):
        return await render_action_form_page(ctx, _default_data(fields), {})
    bulk = ctx.action.name == BULK_EDIT_NAME
    only = None
    if bulk:
        only = {f.name for f in fields if ctx.form.get(CHANGE_PREFIX + f.name)}
        ctx.ticked = only
    data = parse_action_form(ctx.form, fields, only)
    if ctx.select_all and ctx.form.get(FINGERPRINT_FIELD) != selection_fingerprint(ctx.model_admin, ctx.objects):
        return await render_action_form_page(ctx, data, {}, changed=True)
    if bulk:
        if not only:
            errors = {"": [gettext("Choose at least one field to change.")]}
            return await render_action_form_page(ctx, data, errors, status_code=422)
        blocked = bulk_edit_blocked(ctx.admin, ctx.principal, ctx.model_admin, ctx.objects, only)
        if blocked:
            return await render_action_form_page(ctx, data, {}, blocked=blocked, status_code=422)
    errors = validate_action_form(fields, data)
    if bulk:
        # The edit form's own validation, which a host may have extended.
        # Complaints about unticked fields are dropped: they are not the
        # form's to send, exactly as for read-only ones on the edit page.
        for name, messages in ctx.model_admin.validate(data).items():
            if name in only or name == "":
                errors.setdefault(name, []).extend(m for m in messages if m not in errors.get(name, []))
    if errors:
        return await render_action_form_page(ctx, data, errors, status_code=422)
    return data
