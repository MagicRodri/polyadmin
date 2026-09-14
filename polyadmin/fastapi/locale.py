"""Per-request locale resolution and the language switcher's route."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from polyadmin.core.csrf import safe_redirect_path
from polyadmin.fastapi.csrf import make_csrf_route
from polyadmin.fastapi.responses import redirect
from polyadmin.i18n import I18n, use_locale

LOCALE_COOKIE_NAME = "admin_locale"
LOCALE_FORM_FIELD = "locale"
LOCALE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60

_UNSET = object()


def cached_principal(admin: Any, request: Request) -> Any:
    """Authenticate at most once per request: resolving the locale may
    already have, to hand a locale_resolver the principal."""
    if admin.authenticator is None:
        return None
    cached = getattr(request.state, "principal_cache", _UNSET)
    if cached is _UNSET:
        cached = admin.authenticator.authenticate(request)
        request.state.principal_cache = cached
    return cached


def resolve_request_locale(admin: Any, i18n: I18n, request: Request) -> str:
    resolver = None
    if admin.locale_resolver is not None:

        def resolver() -> str | None:
            return admin.locale_resolver(request, cached_principal(admin, request))

    return i18n.resolve(
        request.cookies.get(LOCALE_COOKIE_NAME), resolver, request.headers.get("accept-language")
    )


def make_admin_route(admin: Any, base_path: str, i18n: I18n, renderer: Any) -> type[APIRoute]:
    """The route class for one mounted admin: the locale is resolved and
    installed first, then CSRF runs, so even its failure page is localised.

    A route class, like CSRF's, rather than a dependency: it wraps the
    handler's whole execution, so the context variable is set for the
    handler and everything it calls, and reset afterwards.
    """
    csrf_route = make_csrf_route(admin, base_path)

    class AdminRoute(csrf_route):
        def get_route_handler(self) -> Callable:
            inner = super().get_route_handler()

            async def handler(request: Request) -> Response:
                locale = resolve_request_locale(admin, i18n, request)
                request.state.locale = locale
                request.state.renderer = renderer
                with use_locale(locale, i18n.translator):
                    return await inner(request)

            return handler

    return AdminRoute


def build_locale_handler(i18n: I18n, base_path: str) -> Callable:
    """POST {base}/locale: store the switcher's choice, go back.

    An unsupported value is ignored rather than refused: the redirect is
    the same either way, and there is nothing to explain."""

    async def handler(request: Request) -> Response:
        form = await request.form()
        target = safe_redirect_path(request.headers.get("referer"), request.url.netloc, base_path, base_path)
        response = redirect(request, target)
        locale = i18n.match(form.get(LOCALE_FORM_FIELD))
        if locale:
            response.set_cookie(
                LOCALE_COOKIE_NAME,
                locale,
                max_age=LOCALE_COOKIE_MAX_AGE,
                path=base_path or "/",
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
            )
        return response

    return handler
