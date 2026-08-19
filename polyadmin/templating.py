"""Renderer: turns a ModelAdmin + data into an HTML page.

Three levels of template ownership: framework templates
(this package's `templates/` dir), then application override
directories, searched in the order given, before falling back to the
framework default.

`render_list_fragment` / `render_form_fragment` render just the
interactive inner region (no base layout) for HTMX partial swaps
 -- the full-page and fragment variants share the same
TemplateContext builder, so they never drift out of sync.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import jinja2

from polyadmin.core.admin import Admin
from polyadmin.core.inline import Inline
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.pagination import Page
from polyadmin.core.query import ListRequest
from polyadmin.core.template_context import (
    dashboard_context,
    delete_context,
    detail_context,
    form_context,
    list_context,
)
from polyadmin.ui import ui

# build_inline_context is imported lazily inside the methods that need
# it (not at module level) -- polyadmin.fastapi.inlines lives under
# the polyadmin.fastapi package, whose __init__ imports router.py ->
# handlers.py -> `from polyadmin.templating import Renderer`; an
# eager top-level import here would close that into a real circular
# import (this module partially initialized when fastapi/__init__.py
# tries to import Renderer from it).

FRAMEWORK_TEMPLATES_DIR = Path(__file__).parent / "templates"


class Renderer:
    def __init__(self, *, template_dirs: Iterable[str | Path] = ()) -> None:
        search_dirs = [str(d) for d in template_dirs] + [str(FRAMEWORK_TEMPLATES_DIR)]
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(search_dirs),
            autoescape=jinja2.select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # `ui` resolves shadcn-derived class strings (polyadmin/ui.py).
        # A global rather than a per-template import so every template --
        # including application overrides and custom page/widget
        # templates -- can style with the same vocabulary for free.
        self.env.globals["ui"] = ui

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        return self.env.get_template(template_name).render(**context)

    def render_candidates(self, candidates: Sequence[str], context: dict[str, Any]) -> str:
        return self.env.select_template(candidates).render(**context)

    def render_list(
        self,
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
    ) -> str:
        context = list_context(
            admin,
            model_admin,
            page,
            list_request=list_request,
            permissions=permissions,
            relation_permissions=relation_permissions,
            base_path=base_path,
            messages=messages,
            principal=principal,
        )
        return self.render_candidates(model_admin.get_template_candidates("list"), context)

    def render_list_fragment(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        page: Page,
        *,
        list_request: ListRequest | None = None,
        permissions: dict[str, bool] | None = None,
        relation_permissions: dict[str, bool] | None = None,
        base_path: str = "/admin",
        principal: Any = None,
    ) -> str:
        context = list_context(
            admin,
            model_admin,
            page,
            list_request=list_request,
            permissions=permissions,
            relation_permissions=relation_permissions,
            base_path=base_path,
            principal=principal,
        )
        return self.render("admin/components/list_content.html", context)

    def render_detail(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        obj: Any,
        *,
        principal: Any = None,
        permissions: dict[str, bool] | None = None,
        relation_permissions: dict[str, bool] | None = None,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        from polyadmin.fastapi.inlines import build_inline_context

        context = detail_context(
            admin,
            model_admin,
            obj,
            permissions=permissions,
            relation_permissions=relation_permissions,
            base_path=base_path,
            messages=messages,
            principal=principal,
        )
        context["inlines"] = build_inline_context(admin, principal, model_admin, obj, "readonly", base_path)
        return self.render_candidates(model_admin.get_template_candidates("detail"), context)

    def render_form(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        *,
        principal: Any = None,
        obj: Any | None = None,
        data: dict[str, Any] | None = None,
        errors: dict[str, list[str]] | None = None,
        non_field_errors: list[str] | None = None,
        relation_options: dict[str, list[tuple[Any, Any]]] | None = None,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        from polyadmin.fastapi.auth import compute_permissions
        from polyadmin.fastapi.inlines import build_inline_context

        context = form_context(
            admin,
            model_admin,
            obj=obj,
            data=data,
            errors=errors,
            non_field_errors=non_field_errors,
            relation_options=relation_options,
            permissions=compute_permissions(admin, principal, model_admin),
            base_path=base_path,
            messages=messages,
            principal=principal,
        )
        mode = "placeholder" if obj is None else "edit"
        context["inlines"] = build_inline_context(admin, principal, model_admin, obj, mode, base_path)
        return self.render_candidates(model_admin.get_template_candidates("form"), context)

    def render_form_fragment(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        *,
        principal: Any = None,
        obj: Any | None = None,
        data: dict[str, Any] | None = None,
        errors: dict[str, list[str]] | None = None,
        non_field_errors: list[str] | None = None,
        relation_options: dict[str, list[tuple[Any, Any]]] | None = None,
        base_path: str = "/admin",
    ) -> str:
        from polyadmin.fastapi.auth import compute_permissions
        from polyadmin.fastapi.inlines import build_inline_context

        context = form_context(
            admin,
            model_admin,
            obj=obj,
            data=data,
            errors=errors,
            non_field_errors=non_field_errors,
            relation_options=relation_options,
            permissions=compute_permissions(admin, principal, model_admin),
            base_path=base_path,
            principal=principal,
        )
        mode = "placeholder" if obj is None else "edit"
        context["inlines"] = build_inline_context(admin, principal, model_admin, obj, mode, base_path)
        return self.render("admin/components/form_wrapper.html", context)

    def render_inline_fragment(
        self,
        admin: Admin,
        principal: Any,
        model_admin: ModelAdmin,
        obj: Any,
        inline: Inline,
        *,
        base_path: str = "/admin",
        redisplay: dict[str, Any] | None = None,
    ) -> str:
        """Renders just the one inline section matching `inline.child`,
        standalone -- the response body for the three inline
        create/update/delete routes (see fastapi/handlers.py's
        build_inline_handlers), swapped into `#inline-{child_slug}` via
        HTMX's outerHTML on every mutation.
        """
        from polyadmin.fastapi.inlines import build_inline_context

        sections = build_inline_context(admin, principal, model_admin, obj, "edit", base_path, redisplay=redisplay)
        section = next(s for s in sections if s["slug"] == inline.child)
        return self.render("admin/components/inline_fragment.html", {"admin": admin, "base_path": base_path, "inline": section})

    def render_dashboard(
        self,
        admin: Admin,
        dashboard: Any,
        widgets: list[Any],
        *,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
        principal: Any = None,
    ) -> str:
        context = dashboard_context(admin, dashboard, widgets, base_path=base_path, messages=messages, principal=principal)
        return self.render("admin/dashboard.html", context)

    def render_lookup(self, options: list[tuple[Any, Any]]) -> str:
        return self.render("admin/components/lookup_results.html", {"options": options})

    def render_delete(
        self,
        admin: Admin,
        model_admin: ModelAdmin,
        obj: Any,
        *,
        base_path: str = "/admin",
        messages: list[dict[str, Any]] | None = None,
        principal: Any = None,
    ) -> str:
        context = delete_context(admin, model_admin, obj, base_path=base_path, messages=messages, principal=principal)
        return self.render_candidates(model_admin.get_template_candidates("delete"), context)
