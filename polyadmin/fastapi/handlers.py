"""Request handlers for ModelAdmin CRUD routes.

Each `build_*` function returns endpoint coroutine(s) closing over the
Admin, ModelAdmin, and Renderer they serve; `router.py` wires these onto
routes. This keeps the handlers testable independent of routing.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, StreamingResponse

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.csrf import safe_redirect_path
from polyadmin.core.exporter import Exporter
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.pagination import paginate
from polyadmin.core.query import ListRequest, execute_list_query
from polyadmin.fastapi.auth import authorize, authorize_object, compute_permissions
from polyadmin.fastapi.relations import compute_relation_options, compute_relation_permissions
from polyadmin.fastapi.responses import clear_flash, is_htmx_request, pop_flash, redirect, set_flash
from polyadmin.templating import Renderer

_FILTER_KEY = re.compile(r"^filter\[(\w+)\]$")


def _parse_list_request(query_params: Any) -> ListRequest:
    filters = {}
    for key, value in query_params.multi_items():
        match = _FILTER_KEY.match(key)
        if match:
            filters[match.group(1)] = value
    try:
        page = int(query_params.get("page", 1))
        page_size = int(query_params.get("page_size", 25))
    except ValueError:
        page, page_size = 1, 25
    return ListRequest(
        search=query_params.get("search") or None,
        filters=filters,
        ordering=query_params.get("sort") or None,
        page=page,
        page_size=page_size,
    )


def _validate_writable(model_admin: ModelAdmin, data: dict[str, Any], obj: Any = None) -> dict[str, list[str]]:
    """Run the ModelAdmin's own validation, then drop any complaint about
    a read-only field.

    Such a field is never posted (see _parse_form_data), so a `required`
    read-only field would otherwise fail validation on every save -- the
    value is not missing, it is simply not the form's to send. Wrapping
    rather than changing validate() keeps the ModelAdmin contract as it
    was, so an application's own validate override is unaffected.
    """
    errors = model_admin.validate(data)
    return {name: errs for name, errs in errors.items() if not model_admin.is_readonly(name, obj)}


def _parse_form_data(model_admin: ModelAdmin, form: Any, obj: Any = None) -> dict[str, Any]:
    """Read the posted form into a data map.

    `obj` is the record being edited (None when creating), and is passed
    only so read-only fields can be resolved: a read-only field is
    skipped entirely, so a crafted POST naming it cannot write it.
    Omitting the input from the form is presentation; this is the
    enforcement.
    """
    data: dict[str, Any] = {}
    for name in model_admin.get_form_fields():
        if model_admin.is_readonly(name, obj):
            continue
        field = model_admin.get_field(name)
        if field.field_type == "boolean":
            data[name] = name in form
        elif field.field_type == "manytomany":
            data[name] = form.getlist(name)
        else:
            data[name] = field.parse_form_value(form.get(name))
    return data


def build_list_handler(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    slug = model_admin.get_slug()

    async def list_view(request: Request) -> HTMLResponse:
        principal, error = authorize(admin, request, resource_permission(slug, "list"), model_admin)
        if error:
            return error
        # None: a list page is about the model, not one record.
        permissions = compute_permissions(admin, principal, model_admin, None)
        relation_permissions = compute_relation_permissions(
            admin, principal, model_admin, list(model_admin.list_display)
        )

        list_request = _parse_list_request(request.query_params)
        objects = execute_list_query(model_admin, model_admin.get_queryset(), list_request)
        page = paginate(objects, page=list_request.page, page_size=list_request.page_size)

        if is_htmx_request(request):
            html = renderer.render_list_fragment(
                admin,
                model_admin,
                page,
                list_request=list_request,
                permissions=permissions,
                relation_permissions=relation_permissions,
                base_path=base_path,
                principal=principal,
                csrf_token=request.state.csrf_token,
            )
        else:
            messages = pop_flash(request)
            html = renderer.render_list(
                admin,
                model_admin,
                page,
                list_request=list_request,
                permissions=permissions,
                relation_permissions=relation_permissions,
                base_path=base_path,
                messages=messages,
                principal=principal,
                csrf_token=request.state.csrf_token,
            )
        response = HTMLResponse(html)
        if not is_htmx_request(request):
            clear_flash(response)
        return response

    return list_view


def build_detail_handler(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    slug = model_admin.get_slug()

    async def detail_view(request: Request, pk: str) -> HTMLResponse:
        principal, error = authorize(admin, request, resource_permission(slug, "view"), model_admin)
        if error:
            return error
        obj = model_admin.get_object(pk)
        if obj is None:
            return HTMLResponse("Not found", status_code=404)
        # The record's own page: per-object rules decide whether it
        # offers Edit/Delete at all.
        if not authorize_object(admin, principal, resource_permission(slug, "view"), obj):
            return HTMLResponse("Permission denied.", status_code=403)
        permissions = compute_permissions(admin, principal, model_admin, obj)
        relation_permissions = compute_relation_permissions(
            admin, principal, model_admin, model_admin.get_detail_fields()
        )
        messages = pop_flash(request)
        html = renderer.render_detail(
            admin,
            model_admin,
            obj,
            principal=principal,
            csrf_token=request.state.csrf_token,
            permissions=permissions,
            relation_permissions=relation_permissions,
            base_path=base_path,
            messages=messages,
        )
        response = HTMLResponse(html)
        clear_flash(response)
        return response

    return detail_view


def build_create_handlers(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    slug = model_admin.get_slug()

    async def create_get(request: Request) -> HTMLResponse:
        principal, error = authorize(admin, request, resource_permission(slug, "create"), model_admin)
        if error:
            return error
        relation_options = compute_relation_options(admin, model_admin)
        html = renderer.render_form(
            admin,
            model_admin,
            principal=principal,
            csrf_token=request.state.csrf_token,
            relation_options=relation_options,
            base_path=base_path,
        )
        return HTMLResponse(html)

    async def create_post(request: Request):
        principal, error = authorize(admin, request, resource_permission(slug, "create"), model_admin)
        if error:
            return error
        form = await request.form()
        data = _parse_form_data(model_admin, form)
        errors = _validate_writable(model_admin, data)
        if errors:
            relation_options = compute_relation_options(admin, model_admin)
            if is_htmx_request(request):
                html = renderer.render_form_fragment(
                    admin,
                    model_admin,
                    principal=principal,
                    csrf_token=request.state.csrf_token,
                    data=data,
                    errors=errors,
                    relation_options=relation_options,
                    base_path=base_path,
                )
            else:
                html = renderer.render_form(
                    admin,
                    model_admin,
                    principal=principal,
                    csrf_token=request.state.csrf_token,
                    data=data,
                    errors=errors,
                    relation_options=relation_options,
                    base_path=base_path,
                )
            return HTMLResponse(html, status_code=422)
        obj = model_admin.create(data)
        pk = model_admin.get_pk(obj)
        target = f"{base_path}/{model_admin.get_slug()}/{pk}"
        if form.get("_continue"):
            target += "/edit"
        response = redirect(request, target)
        set_flash(response, "success", f"{model_admin.get_verbose_name()} created.")
        return response

    return create_get, create_post


def build_edit_handlers(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    slug = model_admin.get_slug()

    async def edit_get(request: Request, pk: str) -> HTMLResponse:
        principal, error = authorize(admin, request, resource_permission(slug, "update"), model_admin)
        if error:
            return error
        obj = model_admin.get_object(pk)
        if obj is None:
            return HTMLResponse("Not found", status_code=404)
        if not authorize_object(admin, principal, resource_permission(slug, "update"), obj):
            return HTMLResponse("Permission denied.", status_code=403)
        relation_options = compute_relation_options(admin, model_admin, obj=obj)
        html = renderer.render_form(
            admin,
            model_admin,
            principal=principal,
            csrf_token=request.state.csrf_token,
            obj=obj,
            relation_options=relation_options,
            base_path=base_path,
        )
        return HTMLResponse(html)

    async def edit_post(request: Request, pk: str):
        principal, error = authorize(admin, request, resource_permission(slug, "update"), model_admin)
        if error:
            return error
        obj = model_admin.get_object(pk)
        if obj is None:
            return HTMLResponse("Not found", status_code=404)
        if not authorize_object(admin, principal, resource_permission(slug, "update"), obj):
            return HTMLResponse("Permission denied.", status_code=403)
        form = await request.form()
        data = _parse_form_data(model_admin, form, obj)
        errors = _validate_writable(model_admin, data, obj)
        if errors:
            relation_options = compute_relation_options(admin, model_admin, obj=obj)
            if is_htmx_request(request):
                html = renderer.render_form_fragment(
                    admin,
                    model_admin,
                    principal=principal,
                    csrf_token=request.state.csrf_token,
                    obj=obj,
                    data=data,
                    errors=errors,
                    relation_options=relation_options,
                    base_path=base_path,
                )
            else:
                html = renderer.render_form(
                    admin,
                    model_admin,
                    principal=principal,
                    csrf_token=request.state.csrf_token,
                    obj=obj,
                    data=data,
                    errors=errors,
                    relation_options=relation_options,
                    base_path=base_path,
                )
            return HTMLResponse(html, status_code=422)
        model_admin.update(obj, data)
        target = f"{base_path}/{model_admin.get_slug()}/{pk}"
        if form.get("_continue"):
            target += "/edit"
        response = redirect(request, target)
        set_flash(response, "success", f"{model_admin.get_verbose_name()} updated.")
        return response

    return edit_get, edit_post


def build_delete_handlers(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    slug = model_admin.get_slug()

    async def delete_get(request: Request, pk: str) -> HTMLResponse:
        principal, error = authorize(admin, request, resource_permission(slug, "delete"), model_admin)
        if error:
            return error
        obj = model_admin.get_object(pk)
        if obj is None:
            return HTMLResponse("Not found", status_code=404)
        if not authorize_object(admin, principal, resource_permission(slug, "delete"), obj):
            return HTMLResponse("Permission denied.", status_code=403)
        html = renderer.render_delete(
            admin,
            model_admin,
            obj,
            base_path=base_path,
            principal=principal,
            csrf_token=request.state.csrf_token,
        )
        return HTMLResponse(html)

    async def delete_post(request: Request, pk: str):
        principal, error = authorize(admin, request, resource_permission(slug, "delete"), model_admin)
        if error:
            return error
        obj = model_admin.get_object(pk)
        if obj is not None:
            if not authorize_object(admin, principal, resource_permission(slug, "delete"), obj):
                return HTMLResponse("Permission denied.", status_code=403)
            model_admin.delete(obj)
        response = redirect(request, f"{base_path}/{model_admin.get_slug()}")
        set_flash(response, "success", f"{model_admin.get_verbose_name()} deleted.")
        return response

    async def delete_htmx(request: Request, pk: str) -> HTMLResponse:
        """Row-level delete for the list view's Delete button: removes
        just that row (empty response, `hx-swap="outerHTML"` on the
        `<tr>` makes it vanish) instead of redirecting anywhere.
        """
        principal, error = authorize(admin, request, resource_permission(slug, "delete"), model_admin)
        if error:
            return error
        obj = model_admin.get_object(pk)
        if obj is not None:
            if not authorize_object(admin, principal, resource_permission(slug, "delete"), obj):
                return HTMLResponse("Permission denied.", status_code=403)
            model_admin.delete(obj)
        return HTMLResponse("")

    return delete_get, delete_post, delete_htmx


def build_action_handler(admin: Admin, model_admin: ModelAdmin, base_path: str):
    """POST /{slug}/actions/{action_name} -- runs a ModelAdmin Action
    over the objects named by the `pks` form field. Serves
    both entry points with the same route: the list view's bulk-select
    form posts every checked row's pk, the detail page's per-record
    action buttons post a single-item `pks`.
    """
    slug = model_admin.get_slug()

    async def action_view(request: Request, action_name: str):
        _, error = authorize(admin, request, resource_permission(slug, "view"), model_admin)
        if error:
            return error
        action = model_admin.get_action(action_name)
        if action is None:
            return HTMLResponse("Not found", status_code=404)

        principal = None
        if admin.authenticator is not None:
            principal = admin.authenticator.authenticate(request)
        if action.permission and admin.authorizer is not None:
            if not admin.authorizer.can(principal, resource_permission(slug, action.permission), model_admin):
                return HTMLResponse("Permission denied.", status_code=403)

        form = await request.form()
        pks = form.getlist("pks")
        # Back to wherever the bulk-action form was submitted from
        # (preserving the current search/filter/sort/page), falling
        # back to the bare list URL if there's no Referer to work with.
        #
        # The Referer is attacker-controlled, so it is validated before
        # being used as a redirect target -- see safe_redirect_path.
        redirect_to = safe_redirect_path(
            request.headers.get("referer"),
            request.url.netloc,
            base_path,
            f"{base_path}/{slug}",
        )
        if not pks:
            response = redirect(request, redirect_to)
            set_flash(response, "warning", "No items selected.")
            return response

        objects = [obj for pk in pks if (obj := model_admin.get_object(pk)) is not None]
        message = action.handler(model_admin, objects, principal)
        response = redirect(request, redirect_to)
        set_flash(response, "success", message or f"{action.label} applied to {len(objects)} record(s).")
        return response

    return action_view


def build_lookup_handler(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    """GET /{slug}/lookup?q=... -- an HTML fragment of matching options
    for this resource, meant to be consumed by another resource's
    relation selector. Gated on *this* resource's own
    `.view` permission, since that's what's actually being browsed.
    """
    slug = model_admin.get_slug()

    async def lookup_view(request: Request) -> HTMLResponse:
        _, error = authorize(admin, request, resource_permission(slug, "view"), model_admin)
        if error:
            return error
        query = request.query_params.get("q", "")
        display_name = request.query_params.get("display") or (
            model_admin.search_fields[0] if model_admin.search_fields else None
        )
        display_field = model_admin.get_field(display_name) if display_name else None

        list_request = ListRequest(search=query or None)
        objects = execute_list_query(model_admin, model_admin.get_queryset(), list_request)[:20]
        options = [
            (model_admin.get_pk(obj), display_field.get_value(obj) if display_field else model_admin.get_pk(obj))
            for obj in objects
        ]
        return HTMLResponse(renderer.render_lookup(options))

    return lookup_view


def build_export_handler(admin: Admin, model_admin: ModelAdmin, exporter: Exporter, base_path: str):
    """GET /{slug}/export/{exporter.format} -- exports the *same*
    filtered/ordered dataset the list view would show for the given
    search/filter/sort query params, respecting
    `list_display` as the column set. Gated on the resource's `.export`
    permission, independent of `.view`.
    """
    slug = model_admin.get_slug()

    async def export_view(request: Request):
        _, error = authorize(admin, request, resource_permission(slug, "export"), model_admin)
        if error:
            return error
        list_request = _parse_list_request(request.query_params)
        objects = execute_list_query(model_admin, model_admin.get_queryset(), list_request)
        columns = list(model_admin.list_display)
        filename = f"{slug}.{exporter.file_extension()}"
        return StreamingResponse(
            exporter.stream(admin, model_admin, objects, columns),
            media_type=exporter.content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return export_view


def build_inline_handlers(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    """POST {slug}/{pk}/inlines/{child_slug}[/{child_pk}] and
    DELETE {slug}/{pk}/inlines/{child_slug}/{child_pk} -- create/update/
    delete one inline child row (see core/inline.py, docs/inlines.md).
    Every response carries just the freshly rebuilt whole inline
    section (full-region-swap, matching render_list_fragment/
    render_form_fragment's existing idiom), never a redirect and never
    the whole parent page.
    """
    parent_slug = model_admin.get_slug()

    def _get_inline(child_slug: str):
        return next((i for i in model_admin.inlines if i.child == child_slug), None)

    async def inline_create(request: Request, pk: str, child_slug: str) -> HTMLResponse:
        inline = _get_inline(child_slug)
        if inline is None:
            return HTMLResponse("Not found", status_code=404)
        principal, error = authorize(admin, request, resource_permission(parent_slug, "update"), model_admin)
        if error:
            return error
        parent_obj = model_admin.get_object(pk)
        if parent_obj is None:
            return HTMLResponse("Not found", status_code=404)
        child_admin = admin.get_model_admin(inline.child)
        _, error = authorize(admin, request, resource_permission(inline.child, "create"), child_admin)
        if error:
            return error

        form = await request.form()
        data = _parse_form_data(child_admin, form)
        data[inline.fk_field] = str(model_admin.get_pk(parent_obj))
        errors = child_admin.validate(data)
        if errors:
            html = renderer.render_inline_fragment(
                admin,
                principal,
                model_admin,
                parent_obj,
                inline,
                base_path=base_path,
                redisplay={"pk": None, "data": data, "errors": errors},
            )
            return HTMLResponse(html, status_code=422)

        child_admin.create(data)
        html = renderer.render_inline_fragment(admin, principal, model_admin, parent_obj, inline, base_path=base_path)
        return HTMLResponse(html)

    async def inline_update(request: Request, pk: str, child_slug: str, child_pk: str) -> HTMLResponse:
        inline = _get_inline(child_slug)
        if inline is None:
            return HTMLResponse("Not found", status_code=404)
        principal, error = authorize(admin, request, resource_permission(parent_slug, "update"), model_admin)
        if error:
            return error
        parent_obj = model_admin.get_object(pk)
        if parent_obj is None:
            return HTMLResponse("Not found", status_code=404)
        child_admin = admin.get_model_admin(inline.child)
        _, error = authorize(admin, request, resource_permission(inline.child, "update"), child_admin)
        if error:
            return error
        child_obj = child_admin.get_object(child_pk)
        if child_obj is None:
            return HTMLResponse("Not found", status_code=404)

        form = await request.form()
        data = _parse_form_data(child_admin, form)
        data[inline.fk_field] = str(model_admin.get_pk(parent_obj))
        errors = child_admin.validate(data)
        if errors:
            html = renderer.render_inline_fragment(
                admin,
                principal,
                model_admin,
                parent_obj,
                inline,
                base_path=base_path,
                redisplay={"pk": child_pk, "data": data, "errors": errors},
            )
            return HTMLResponse(html, status_code=422)

        child_admin.update(child_obj, data)
        html = renderer.render_inline_fragment(admin, principal, model_admin, parent_obj, inline, base_path=base_path)
        return HTMLResponse(html)

    async def inline_delete(request: Request, pk: str, child_slug: str, child_pk: str) -> HTMLResponse:
        inline = _get_inline(child_slug)
        if inline is None:
            return HTMLResponse("Not found", status_code=404)
        principal, error = authorize(admin, request, resource_permission(parent_slug, "update"), model_admin)
        if error:
            return error
        parent_obj = model_admin.get_object(pk)
        if parent_obj is None:
            return HTMLResponse("Not found", status_code=404)
        child_admin = admin.get_model_admin(inline.child)
        _, error = authorize(admin, request, resource_permission(inline.child, "delete"), child_admin)
        if error:
            return error
        child_obj = child_admin.get_object(child_pk)
        if child_obj is not None:
            child_admin.delete(child_obj)

        html = renderer.render_inline_fragment(admin, principal, model_admin, parent_obj, inline, base_path=base_path)
        return HTMLResponse(html)

    return inline_create, inline_update, inline_delete
