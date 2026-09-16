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

from polyadmin.core._async import maybe_await
from polyadmin.core.action import DELETE_SELECTED_NAME
from polyadmin.core.admin import Admin
from polyadmin.core.audit import AUDIT_CREATE, AUDIT_DELETE, AUDIT_UPDATE
from polyadmin.core.authorization import resource_permission
from polyadmin.core.csrf import safe_redirect_path
from polyadmin.core.delete import previews_deletes, resolve_delete_preview
from polyadmin.core.exporter import Exporter
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.pagination import page_of
from polyadmin.core.query import ListRequest, alist_objects, apply_defaults
from polyadmin.core.template_context import delete_preview_view
from polyadmin.fastapi.audit import record_audit
from polyadmin.fastapi.auth import authorize, authorize_object, compute_permissions
from polyadmin.fastapi.deletes import RETURN_FIELD, confirm_delete_selected
from polyadmin.fastapi.errors import forbidden, not_found
from polyadmin.fastapi.locale import acached_principal
from polyadmin.fastapi.relations import (
    compute_relation_options,
    compute_relation_permissions,
)
from polyadmin.fastapi.responses import (
    clear_flash,
    is_htmx_request,
    pop_flash,
    redirect,
    set_flash,
)
from polyadmin.i18n import gettext, ngettext
from polyadmin.templating import Renderer

# The submit buttons meaning something other than "save and show me the
# record". An unclicked submit button's name never reaches the server, so
# the handler reads presence rather than a value.
SAVE_CONTINUE_FIELD = "_continue"
SAVE_ADD_ANOTHER_FIELD = "_addanother"

_FILTER_KEY = re.compile(r"^filter\[(\w+)\]$")


def _parse_list_request(query_params: Any) -> ListRequest:
    filters = {}
    for key, value in query_params.multi_items():
        match = _FILTER_KEY.match(key)
        if match:
            filters[match.group(1)] = value
    # page_size defaults to 0, not 25: an unset value has to reach
    # apply_defaults so the ModelAdmin's own list_per_page is consulted
    # first.
    try:
        page = int(query_params.get("page", 1))
        page_size = int(query_params.get("page_size", 0))
    except ValueError:
        page, page_size = 1, 0
    return ListRequest(
        search=query_params.get("search") or None,
        filters=filters,
        ordering=query_params.get("sort") or None,
        page=page,
        page_size=page_size,
    )


# The autocomplete caps its suggestions: it is a search box, not a
# browser, and past a screenful the answer is "type more".
LOOKUP_LIMIT = 20

# The hidden flag the bulk-actions form sets when the user chose "select
# all N matching" rather than ticking rows.
SELECT_ALL_FIELD = "_select_all"


def _parse_list_request_from_form(form: Any) -> ListRequest:
    """Rebuild the list query from the posted form, not the URL: a bulk action
    posts to its own route, so reading the query string would silently act on
    the unfiltered set.
    """
    filters = {
        match.group(1): value
        for key, value in form.items()
        if (match := _FILTER_KEY.match(key))
    }
    return ListRequest(
        search=form.get("search") or None,
        filters=filters,
        ordering=form.get("sort") or None,
    )


def _validate_writable(model_admin: ModelAdmin, data: dict[str, Any], obj: Any = None) -> dict[str, list[str]]:
    """Run the ModelAdmin's validation, then drop complaints about read-only
    fields.

    Such a field is never posted, so a required one would otherwise fail every
    save: the value is not missing, it is simply not the form's to send.
    Wrapping rather than changing validate() leaves an application's own
    override unaffected.
    """
    errors = model_admin.validate(data)
    return {name: errs for name, errs in errors.items() if not model_admin.is_readonly(name, obj)}


def _parse_form_data(model_admin: ModelAdmin, form: Any, obj: Any = None) -> dict[str, Any]:
    """Read the posted form into a data map.

    `obj` is the record being edited, None when creating, and is passed only to
    resolve read-only fields: such a field is skipped entirely, so a crafted
    POST naming it cannot write it. Omitting the input is presentation; this is
    the enforcement.
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
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "list"), model_admin)
        if error:
            return error
        # None: a list page is about the model, not one record.
        permissions = compute_permissions(admin, principal, model_admin, None)
        relation_permissions = compute_relation_permissions(
            admin, principal, model_admin, list(model_admin.list_display)
        )

        # Resolved once and handed to both the query and the pager:
        # otherwise page_of would size the control from the raw request
        # and disagree with the rows fetched.
        list_request = apply_defaults(model_admin, _parse_list_request(request.query_params))
        objects, total = await alist_objects(model_admin, list_request)
        page = page_of(objects, total, list_request)

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
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "view"), model_admin)
        if error:
            return error
        obj = await maybe_await(model_admin.get_object(pk))
        if obj is None:
            return not_found(request, admin, base_path)
        # The record's own page: per-object rules decide whether it
        # offers Edit/Delete at all.
        if not authorize_object(admin, principal, resource_permission(slug, "view"), obj):
            return forbidden(request, admin, base_path)
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
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "create"), model_admin)
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
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "create"), model_admin)
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
        obj = await maybe_await(model_admin.create(data))
        record_audit(admin, principal, model_admin, AUDIT_CREATE, obj)
        # "Save and add another" goes back to an empty form, checked
        # before building the record's URL since it never uses one.
        # Translators: %(name)s is the model's name. French and Russian
        # nouns carry gender, so phrase around agreement.
        created_message = gettext("%(name)s created.") % {"name": gettext(model_admin.get_verbose_name())}
        if form.get(SAVE_ADD_ANOTHER_FIELD):
            response = redirect(request, f"{base_path}/{model_admin.get_slug()}/create")
            set_flash(response, "success", created_message)
            return response
        pk = model_admin.get_pk(obj)
        target = f"{base_path}/{model_admin.get_slug()}/{pk}"
        if form.get(SAVE_CONTINUE_FIELD):
            target += "/edit"
        response = redirect(request, target)
        set_flash(response, "success", created_message)
        return response

    return create_get, create_post


def build_edit_handlers(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    slug = model_admin.get_slug()

    async def edit_get(request: Request, pk: str) -> HTMLResponse:
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "update"), model_admin)
        if error:
            return error
        obj = await maybe_await(model_admin.get_object(pk))
        if obj is None:
            return not_found(request, admin, base_path)
        if not authorize_object(admin, principal, resource_permission(slug, "update"), obj):
            return forbidden(request, admin, base_path)
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
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "update"), model_admin)
        if error:
            return error
        obj = await maybe_await(model_admin.get_object(pk))
        if obj is None:
            return not_found(request, admin, base_path)
        if not authorize_object(admin, principal, resource_permission(slug, "update"), obj):
            return forbidden(request, admin, base_path)
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
        await maybe_await(model_admin.update(obj, data))
        record_audit(admin, principal, model_admin, AUDIT_UPDATE, obj)
        # Translators: %(name)s is the model's name. French and Russian
        # nouns carry gender, so phrase around agreement.
        updated_message = gettext("%(name)s updated.") % {"name": gettext(model_admin.get_verbose_name())}
        if form.get(SAVE_ADD_ANOTHER_FIELD):
            response = redirect(request, f"{base_path}/{model_admin.get_slug()}/create")
            set_flash(response, "success", updated_message)
            return response
        target = f"{base_path}/{model_admin.get_slug()}/{pk}"
        if form.get(SAVE_CONTINUE_FIELD):
            target += "/edit"
        response = redirect(request, target)
        set_flash(response, "success", updated_message)
        return response

    return edit_get, edit_post


def build_delete_handlers(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    slug = model_admin.get_slug()

    async def delete_get(request: Request, pk: str) -> HTMLResponse:
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "delete"), model_admin)
        if error:
            return error
        obj = await maybe_await(model_admin.get_object(pk))
        if obj is None:
            return not_found(request, admin, base_path)
        if not authorize_object(admin, principal, resource_permission(slug, "delete"), obj):
            return forbidden(request, admin, base_path)
        preview = resolve_delete_preview(admin, model_admin, principal, [obj])
        html = renderer.render_delete(
            admin,
            model_admin,
            obj,
            base_path=base_path,
            principal=principal,
            csrf_token=request.state.csrf_token,
            preview=preview,
        )
        return HTMLResponse(html)

    async def delete_post(request: Request, pk: str):
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "delete"), model_admin)
        if error:
            return error
        obj = await maybe_await(model_admin.get_object(pk))
        if obj is not None:
            if not authorize_object(admin, principal, resource_permission(slug, "delete"), obj):
                return forbidden(request, admin, base_path)
            if resolve_delete_preview(admin, model_admin, principal, [obj]).blocked:
                # Back to the delete page, which says why; redirect() sends
                # HX-Redirect for the htmx route and a 303 otherwise.
                return redirect(request, f"{base_path}/{slug}/{model_admin.get_pk(obj)}/delete")
            await maybe_await(model_admin.delete(obj))
            record_audit(admin, principal, model_admin, AUDIT_DELETE, obj)
        response = redirect(request, f"{base_path}/{model_admin.get_slug()}")
        # Translators: %(name)s is the model's name. French and Russian
        # nouns carry gender, so phrase around agreement.
        deleted_message = gettext("%(name)s deleted.") % {"name": gettext(model_admin.get_verbose_name())}
        set_flash(response, "success", deleted_message)
        return response

    async def delete_htmx(request: Request, pk: str) -> HTMLResponse:
        """Row-level delete for the list view's Delete button: removes just that
        row (an empty response, with `hx-swap="outerHTML"` on the `<tr>`)
        instead of redirecting anywhere.
        """
        principal, error = await authorize(admin, request, base_path, resource_permission(slug, "delete"), model_admin)
        if error:
            return error
        obj = await maybe_await(model_admin.get_object(pk))
        if obj is not None:
            if not authorize_object(admin, principal, resource_permission(slug, "delete"), obj):
                return forbidden(request, admin, base_path)
            if resolve_delete_preview(admin, model_admin, principal, [obj]).blocked:
                # Back to the delete page, which says why; redirect() sends
                # HX-Redirect for the htmx route and a 303 otherwise.
                return redirect(request, f"{base_path}/{slug}/{model_admin.get_pk(obj)}/delete")
            await maybe_await(model_admin.delete(obj))
            record_audit(admin, principal, model_admin, AUDIT_DELETE, obj)
        return HTMLResponse("")

    return delete_get, delete_post, delete_htmx


def build_action_handler(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    """POST /{slug}/actions/{action_name}, running an Action over the objects
    named by the `pks` form field. One route for both entry points: the list's
    bulk-select form posts every checked row, a detail page's action button
    posts a single-item `pks`.
    """
    slug = model_admin.get_slug()

    async def action_view(request: Request, action_name: str):
        _, error = await authorize(admin, request, base_path, resource_permission(slug, "view"), model_admin)
        if error:
            return error
        action = model_admin.get_action(action_name)
        if action is None:
            return not_found(request, admin, base_path)

        principal = await acached_principal(admin, request)
        if (
            action.permission
            and admin.authorizer is not None
            and not admin.authorizer.can(
                principal, resource_permission(slug, action.permission), model_admin
            )
        ):
            return forbidden(request, admin, base_path)

        form = await request.form()
        pks = form.getlist("pks")
        # Back to wherever the form was submitted from, preserving
        # search/filter/sort/page, or the bare list URL if there is no
        # Referer. The Referer is attacker-controlled, so it is validated
        # first -- see safe_redirect_path.
        redirect_to = safe_redirect_path(
            request.headers.get("referer"),
            request.url.netloc,
            base_path,
            f"{base_path}/{slug}",
        )
        # A confirmed delete_selected posts from its own confirmation page, so
        # it carries the original target in _return (validated the same way).
        if form.get(RETURN_FIELD):
            redirect_to = safe_redirect_path(form.get(RETURN_FIELD), request.url.netloc, base_path, f"{base_path}/{slug}")
        # "Select all N matching" posts the filters instead of the pks: a
        # checkbox only reaches the rows on screen. The set is resolved
        # server-side from the same query the list was showing.
        select_all = bool(form.get(SELECT_ALL_FIELD))
        if not select_all and not pks:
            response = redirect(request, redirect_to)
            set_flash(response, "warning", gettext("No items selected."))
            return response

        list_request = None
        if select_all:
            list_request = _parse_list_request_from_form(form)
            list_request.unlimited = True
            objects, _ = await alist_objects(model_admin, list_request)
        else:
            objects = [obj for pk in pks if (obj := await maybe_await(model_admin.get_object(pk))) is not None]
        if not objects:
            response = redirect(request, redirect_to)
            set_flash(response, "warning", gettext("No items selected."))
            return response
        if action.name == DELETE_SELECTED_NAME and previews_deletes(model_admin):
            page = confirm_delete_selected(
                request, form, admin, model_admin, renderer, principal, objects, select_all, redirect_to, list_request, base_path
            )
            if page is not None:
                return page
        message = action.handler(model_admin, objects, principal)
        # One entry per record, not per action: the log's question is
        # "what happened to this record", and a bulk run over 500 rows is
        # 500 answers to it.
        for obj in objects:
            record_audit(admin, principal, model_admin, action.name, obj)
        if message:
            # A host's static message translates from its catalog; one it
            # already translated with gettext misses and passes through.
            message = gettext(message)
        else:
            message = ngettext(
                "%(label)s applied to %(num)d record.", "%(label)s applied to %(num)d records.", len(objects)
            ) % {"label": gettext(action.label), "num": len(objects)}
        response = redirect(request, redirect_to)
        set_flash(response, "success", message)
        return response

    return action_view


def build_lookup_handler(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    """GET /{slug}/lookup?q=..., an HTML fragment of matching options consumed by
    another resource's relation selector. Gated on this resource's own `.view`
    permission, since that is what is being browsed.
    """
    slug = model_admin.get_slug()

    async def lookup_view(request: Request) -> HTMLResponse:
        _, error = await authorize(admin, request, base_path, resource_permission(slug, "view"), model_admin)
        if error:
            return error
        query = request.query_params.get("q", "")
        display_name = request.query_params.get("display") or (
            model_admin.search_fields[0] if model_admin.search_fields else None
        )
        display_field = model_admin.get_field(display_name) if display_name else None

        # The cap rides in as the page window rather than a slice
        # afterwards, so a list_page applies it in its own query instead
        # of returning the whole table to trim.
        list_request = ListRequest(search=query or None, page=1, page_size=LOOKUP_LIMIT)
        objects, _ = await alist_objects(model_admin, list_request)
        options = [
            (model_admin.get_pk(obj), display_field.get_value(obj) if display_field else model_admin.get_pk(obj))
            for obj in objects
        ]
        return HTMLResponse(renderer.render_lookup(options))

    return lookup_view


def build_export_handler(admin: Admin, model_admin: ModelAdmin, exporter: Exporter, base_path: str):
    """GET /{slug}/export/{exporter.format}, exporting the same filtered and
    ordered dataset the list view would show, with `list_display` as the column
    set. Gated on `.export`, independently of `.view`.
    """
    slug = model_admin.get_slug()

    async def export_view(request: Request):
        _, error = await authorize(admin, request, base_path, resource_permission(slug, "export"), model_admin)
        if error:
            return error
        # unlimited: an export of a filtered set is the whole set, not
        # whichever page the user happened to be looking at.
        list_request = _parse_list_request(request.query_params)
        list_request.unlimited = True
        objects, _ = await alist_objects(model_admin, list_request)
        columns = list(model_admin.list_display)
        # Computed here, not inside the generator: the route wrapper resets
        # the locale context variable as soon as this handler returns, and
        # StreamingResponse only iterates the generator afterwards.
        header = [gettext(model_admin.get_field(name).label) for name in columns]
        filename = f"{slug}.{exporter.file_extension()}"
        return StreamingResponse(
            exporter.stream(admin, model_admin, objects, columns, header=header),
            media_type=exporter.content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return export_view


def build_inline_handlers(admin: Admin, model_admin: ModelAdmin, renderer: Renderer, base_path: str):
    """The inline create/update/delete routes. Every response carries the rebuilt
    inline section alone -- never a redirect, never the whole parent page --
    matching the other fragment routes.
    """
    parent_slug = model_admin.get_slug()

    def _get_inline(child_slug: str):
        return next((i for i in model_admin.inlines if i.child == child_slug), None)

    async def inline_create(request: Request, pk: str, child_slug: str) -> HTMLResponse:
        inline = _get_inline(child_slug)
        if inline is None:
            return not_found(request, admin, base_path)
        principal, error = await authorize(admin, request, base_path, resource_permission(parent_slug, "update"), model_admin)
        if error:
            return error
        parent_obj = await maybe_await(model_admin.get_object(pk))
        if parent_obj is None:
            return not_found(request, admin, base_path)
        child_admin = admin.get_model_admin(inline.child)
        _, error = await authorize(admin, request, base_path, resource_permission(inline.child, "create"), child_admin)
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

        await maybe_await(child_admin.create(data))
        html = renderer.render_inline_fragment(admin, principal, model_admin, parent_obj, inline, base_path=base_path)
        return HTMLResponse(html)

    async def inline_update(request: Request, pk: str, child_slug: str, child_pk: str) -> HTMLResponse:
        inline = _get_inline(child_slug)
        if inline is None:
            return not_found(request, admin, base_path)
        principal, error = await authorize(admin, request, base_path, resource_permission(parent_slug, "update"), model_admin)
        if error:
            return error
        parent_obj = await maybe_await(model_admin.get_object(pk))
        if parent_obj is None:
            return not_found(request, admin, base_path)
        child_admin = admin.get_model_admin(inline.child)
        _, error = await authorize(admin, request, base_path, resource_permission(inline.child, "update"), child_admin)
        if error:
            return error
        child_obj = await maybe_await(child_admin.get_object(child_pk))
        if child_obj is None:
            return not_found(request, admin, base_path)

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

        await maybe_await(child_admin.update(child_obj, data))
        html = renderer.render_inline_fragment(admin, principal, model_admin, parent_obj, inline, base_path=base_path)
        return HTMLResponse(html)

    async def inline_delete(request: Request, pk: str, child_slug: str, child_pk: str) -> HTMLResponse:
        inline = _get_inline(child_slug)
        if inline is None:
            return not_found(request, admin, base_path)
        principal, error = await authorize(admin, request, base_path, resource_permission(parent_slug, "update"), model_admin)
        if error:
            return error
        parent_obj = await maybe_await(model_admin.get_object(pk))
        if parent_obj is None:
            return not_found(request, admin, base_path)
        child_admin = admin.get_model_admin(inline.child)
        _, error = await authorize(admin, request, base_path, resource_permission(inline.child, "delete"), child_admin)
        if error:
            return error
        child_obj = await maybe_await(child_admin.get_object(child_pk))
        if child_obj is not None:
            preview = resolve_delete_preview(admin, child_admin, principal, [child_obj])
            if preview.blocked:
                # 200 with the rebuilt section and the reason on top: htmx
                # would drop a 4xx body, and a redirect would lose the
                # parent form's unsaved edits.
                html = renderer.render_inline_fragment(
                    admin, principal, model_admin, parent_obj, inline, base_path=base_path,
                    refusal=delete_preview_view(preview, base_path),
                )
                return HTMLResponse(html)
            await maybe_await(child_admin.delete(child_obj))

        html = renderer.render_inline_fragment(admin, principal, model_admin, parent_obj, inline, base_path=base_path)
        return HTMLResponse(html)

    return inline_create, inline_update, inline_delete
