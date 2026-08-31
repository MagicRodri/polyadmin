"""FastAPI adapter: mounts an Admin as an APIRouter.

    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")

`base_path` must match the `prefix` passed to `include_router` — it's
used to build the links rendered inside templates (nav, pagination,
redirects). The two aren't derived from each other because the router
is built before FastAPI knows where it will be mounted.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import DASHBOARD_VIEW
from polyadmin.core.exporter import CSVExporter, XLSXExporter
from polyadmin.fastapi.auth import authorize
from polyadmin.fastapi.csrf import make_csrf_route
from polyadmin.fastapi.handlers import (
    build_action_handler,
    build_create_handlers,
    build_delete_handlers,
    build_detail_handler,
    build_edit_handlers,
    build_export_handler,
    build_inline_handlers,
    build_list_handler,
    build_lookup_handler,
)
from polyadmin.fastapi.inlines import validate_inlines
from polyadmin.fastapi.pages import build_page_handler
from polyadmin.fastapi.responses import clear_flash, pop_flash
from polyadmin.fastapi.static import mount_static
from polyadmin.templating import Renderer

DEFAULT_EXPORTERS = [CSVExporter(), XLSXExporter()]


def create_router(
    admin: Admin,
    *,
    base_path: str = "/admin",
    template_dirs: tuple[str | Path, ...] = (),
    static_dir: str | Path | None = None,
    exporters: tuple = tuple(DEFAULT_EXPORTERS),
) -> APIRouter:
    renderer = Renderer(template_dirs=template_dirs)
    # route_class, not a dependency: see polyadmin/fastapi/csrf.py.
    router = APIRouter(route_class=make_csrf_route(admin, base_path))

    mount_static(router, static_dir=static_dir)

    @router.get("", include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        principal, error = authorize(admin, request, DASHBOARD_VIEW)
        if error:
            return error

        if admin.dashboard is not None:
            widgets = admin.dashboard.get_widgets(principal, admin.authorizer)
            messages = pop_flash(request)
            html = renderer.render_dashboard(admin, admin.dashboard, widgets, base_path=base_path, messages=messages, principal=principal)
            response = HTMLResponse(html)
            clear_flash(response)
            return response

        # No Dashboard configured -- land on the first viewable resource.
        for model_admin in admin.model_admins:
            if model_admin.can_view:
                return RedirectResponse(f"{base_path}/{model_admin.get_slug()}")
        return HTMLResponse("<p>No resources registered.</p>")

    for model_admin in admin.model_admins:
        prefix = f"/{model_admin.get_slug()}"

        if model_admin.can_view:
            router.add_api_route(
                prefix, build_list_handler(admin, model_admin, renderer, base_path), methods=["GET"]
            )

        if model_admin.can_create:
            create_get, create_post = build_create_handlers(admin, model_admin, renderer, base_path)
            router.add_api_route(f"{prefix}/create", create_get, methods=["GET"])
            router.add_api_route(f"{prefix}/create", create_post, methods=["POST"])

        if model_admin.can_export:
            for exporter in exporters:
                router.add_api_route(
                    f"{prefix}/export/{exporter.format}",
                    build_export_handler(admin, model_admin, exporter, base_path),
                    methods=["GET"],
                )

        if model_admin.can_view:
            router.add_api_route(
                f"{prefix}/lookup",
                build_lookup_handler(admin, model_admin, renderer, base_path),
                methods=["GET"],
            )
            if model_admin.actions:
                router.add_api_route(
                    f"{prefix}/actions/{{action_name}}",
                    build_action_handler(admin, model_admin, base_path),
                    methods=["POST"],
                )
            router.add_api_route(
                f"{prefix}/{{pk}}",
                build_detail_handler(admin, model_admin, renderer, base_path),
                methods=["GET"],
            )

        if model_admin.can_update:
            edit_get, edit_post = build_edit_handlers(admin, model_admin, renderer, base_path)
            router.add_api_route(f"{prefix}/{{pk}}/edit", edit_get, methods=["GET"])
            router.add_api_route(f"{prefix}/{{pk}}/edit", edit_post, methods=["POST"])

        if model_admin.can_delete:
            delete_get, delete_post, delete_htmx = build_delete_handlers(admin, model_admin, renderer, base_path)
            router.add_api_route(f"{prefix}/{{pk}}/delete", delete_get, methods=["GET"])
            router.add_api_route(f"{prefix}/{{pk}}/delete", delete_post, methods=["POST"])
            router.add_api_route(f"{prefix}/{{pk}}/delete", delete_htmx, methods=["DELETE"])

        if model_admin.inlines:
            validate_inlines(admin, model_admin)
            inline_create, inline_update, inline_delete = build_inline_handlers(admin, model_admin, renderer, base_path)
            router.add_api_route(f"{prefix}/{{pk}}/inlines/{{child_slug}}", inline_create, methods=["POST"])
            router.add_api_route(f"{prefix}/{{pk}}/inlines/{{child_slug}}/{{child_pk}}", inline_update, methods=["POST"])
            router.add_api_route(f"{prefix}/{{pk}}/inlines/{{child_slug}}/{{child_pk}}", inline_delete, methods=["DELETE"])

    for page in admin.pages:
        router.add_api_route(
            page.path, build_page_handler(admin, page, renderer, base_path), methods=list(page.methods)
        )

    return router
