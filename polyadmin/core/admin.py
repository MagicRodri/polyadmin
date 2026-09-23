"""Admin: the root object mounted by the host application.

Owns the ModelAdmin registry, the AdminPage registry (custom routes
registered via `route()`), and the authenticator/authorizer/dashboard
wiring. CRUD/page route generation and template/static configuration
live in the framework adapters (e.g. polyadmin.fastapi), not here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
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
        site_favicon_url: str | None = None,
        disable_csrf: bool = False,
        audit_logger: Any | None = None,
        login_backend: Any | None = None,
        default_locale: str = "en",
        locales: Sequence[str] = (),
        locale_resolver: Callable[[Any, Any], str | None] | None = None,
        catalogs: Sequence[tuple[str | Path, str]] = (),
        translator: Any | None = None,
        locale_names: Mapping[str, str] | None = None,
        locale_switcher: bool = True,
        pseudo_locale: bool = False,
    ) -> None:
        self.dashboard = dashboard
        self.authenticator = authenticator
        self.authorizer = authorizer
        self.site_title = site_title
        self.site_logo_url = site_logo_url
        self.site_favicon_url = site_favicon_url
        # Opt-out, never opt-in: a security control that defaults to off
        # is one nobody turns on. The token cookie is still minted when
        # this is set, so templates and custom pages behave identically.
        self.disable_csrf = disable_csrf
        # When set, receives an entry for every create, update, delete
        # and action. None means nothing is recorded -- the framework
        # does not store a log itself. See core/audit.py.
        self.audit_logger = audit_logger
        # When set, mounts the built-in login page and makes an
        # unauthenticated request redirect there instead of returning
        # 401. None leaves both behaviours off -- see core/login.py.
        self.login_backend = login_backend
        # Internationalisation -- see polyadmin/i18n and docs/i18n.md. The
        # defaults serve English plus every framework catalog (fr, ru),
        # resolved per request, with the language switcher shown.
        # locale_resolver(request, principal) gets the request's
        # authenticated principal on every page, login and error pages
        # included -- None only without a session or an authenticator.
        self.default_locale = default_locale
        self.locales = list(locales)
        self.locale_resolver = locale_resolver
        self.catalogs = list(catalogs)
        self.translator = translator
        self.locale_names = dict(locale_names or {})
        self.locale_switcher = locale_switcher
        self.pseudo_locale = pseudo_locale
        self._registry: dict[str, ModelAdmin] = {}
        self._pages: dict[str, AdminPage] = {}
        for model_admin in model_admins:
            self.register(model_admin)

    def register(self, model_admin: ModelAdmin) -> None:
        slug = model_admin.get_slug()
        if slug in self._registry:
            raise ValueError(f"A ModelAdmin is already registered for slug {slug!r}.")
        model_admin.validate_detail_actions()
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
