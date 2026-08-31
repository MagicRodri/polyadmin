"""FastAPI wiring for AdminPage: a custom admin route with its own
template and handler, for functionality that isn't resource CRUD
(reports, wizards, internal tools). See docs/routing.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from polyadmin.core.admin import Admin
from polyadmin.core.page import AdminPage
from polyadmin.core.template_context import base_context, category_breadcrumb
from polyadmin.fastapi.auth import authorize
from polyadmin.fastapi.responses import clear_flash, is_htmx_request, pop_flash, redirect, set_flash
from polyadmin.templating import Renderer


@dataclass
class PageContext:
    """What an AdminPage's handler receives -- the raw Request (for
    form/query parsing, exactly like any other FastAPI handler) plus
    render/redirect helpers reusing the framework's own layout, flash
    cookie, and HTMX-aware redirect.
    """

    admin: Admin
    page: AdminPage
    request: Request
    principal: Any
    renderer: Renderer
    base_path: str

    @property
    def is_htmx(self) -> bool:
        return is_htmx_request(self.request)

    async def form(self) -> Any:
        return await self.request.form()

    def render(self, template_name: str, *, status_code: int = 200, **extra: Any) -> HTMLResponse:
        """Render template_name (an application-supplied template
        extending "admin/base.html", resolved via the same
        template_dirs search Jinja already uses for resource
        overrides) inside the shared admin layout.
        """
        context = {
            **base_context(
                self.admin,
                base_path=self.base_path,
                messages=pop_flash(self.request),
                breadcrumbs=[
                    *category_breadcrumb(self.page.category),
                    {"label": self.page.label, "url": None, "active": True},
                ],
                active_nav_key=f"page:{self.page.path}",
                # getattr, not attribute access: mirrors the Fiber
                # adapter's csrfToken(c), which yields "" rather than
                # failing if a page is somehow rendered outside the
                # mounted router that sets it.
                csrf_token=getattr(self.request.state, "csrf_token", ""),
            ),
            "page": self.page,
            **extra,
        }
        html = self.renderer.render(template_name, context)
        response = HTMLResponse(html, status_code=status_code)
        clear_flash(response)
        return response

    def redirect(self, url: str, *, flash: tuple[str, str] | None = None) -> Response:
        response = redirect(self.request, url)
        if flash:
            set_flash(response, *flash)
        return response


def build_page_handler(admin: Admin, page: AdminPage, renderer: Renderer, base_path: str):
    async def handler(request: Request):
        principal, error = authorize(admin, request, page.permission, page)
        if error:
            return error
        ctx = PageContext(
            admin=admin, page=page, request=request, principal=principal, renderer=renderer, base_path=base_path
        )
        return await page.handler(ctx)

    return handler
