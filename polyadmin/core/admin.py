"""Admin: the root object mounted by the host application.

Owns the ModelAdmin registry, the AdminPage registry (custom routes
registered via `route()`), and the authenticator/authorizer/dashboard
wiring. CRUD/page route generation and template/static configuration
live in the framework adapters (e.g. polyadmin.fastapi), not here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.page import AdminPage, PageHandler


class Admin:
    """Root admin application: owns the ModelAdmin and AdminPage registries."""

    def __init__(
        self,
        model_admins: Iterable[ModelAdmin] = (),
        *,
        dashboard: Any | None = None,
        authenticator: Any | None = None,
        authorizer: Any | None = None,
        site_title: str = "PolyAdmin",
        site_logo_url: str | None = None,
    ) -> None:
        self.dashboard = dashboard
        self.authenticator = authenticator
        self.authorizer = authorizer
        self.site_title = site_title
        self.site_logo_url = site_logo_url
        self._registry: dict[str, ModelAdmin] = {}
        self._pages: dict[str, AdminPage] = {}
        for model_admin in model_admins:
            self.register(model_admin)

    def register(self, model_admin: ModelAdmin) -> None:
        slug = model_admin.get_slug()
        if slug in self._registry:
            raise ValueError(f"A ModelAdmin is already registered for slug {slug!r}.")
        self._registry[slug] = model_admin

    def get_model_admin(self, slug: str) -> ModelAdmin:
        try:
            return self._registry[slug]
        except KeyError:
            raise KeyError(f"No ModelAdmin registered for slug {slug!r}.") from None

    @property
    def model_admins(self) -> list[ModelAdmin]:
        return list(self._registry.values())

    def route(
        self,
        path: str,
        handler: PageHandler,
        *,
        label: str | None = None,
        category: str | None = None,
        icon: str = "collection",
        permission: str | None = None,
        methods: tuple[str, ...] = ("GET", "POST"),
        show_in_nav: bool = True,
    ) -> AdminPage:
        """Register a custom admin page -- for functionality that isn't
        resource CRUD (reports, wizards, internal tools). See
        docs/routing.md.
        """
        page = AdminPage(
            path,
            handler,
            label=label,
            category=category,
            icon=icon,
            permission=permission,
            methods=methods,
            show_in_nav=show_in_nav,
        )
        if page.path in self._pages:
            raise ValueError(f"A page is already registered for path {page.path!r}.")
        self._pages[page.path] = page
        return page

    @property
    def pages(self) -> list[AdminPage]:
        return list(self._pages.values())
