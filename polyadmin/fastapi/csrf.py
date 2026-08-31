"""Double-submit CSRF protection for the admin router.

Implemented as a custom APIRoute rather than a dependency: every handler
here returns an HTMLResponse or RedirectResponse *directly*, and FastAPI
does not merge a dependency's response headers into a response the
handler returned itself -- the cookie would be silently dropped. A route
class wraps the endpoint and post-processes the real response, which is
the idiomatic seam for this.

Mirrors go-polyadmin/fiber/csrf.go. See
.idea/superpowers/specs/2026-09-01-csrf-hardening-design.md.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute

from polyadmin.core.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FIELD_NAME,
    CSRF_HEADER_NAME,
    csrf_tokens_match,
    is_safe_method,
    new_csrf_token,
)


def make_csrf_route(admin, base_path: str) -> type[APIRoute]:
    """Build the APIRoute subclass for one mounted admin."""

    class CSRFRoute(APIRoute):
        def get_route_handler(self) -> Callable:
            original = super().get_route_handler()

            async def handler(request: Request) -> Response:
                cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
                token = cookie_token or new_csrf_token()
                # Handlers and the renderer read the token from here.
                request.state.csrf_token = token

                if not admin.disable_csrf and not is_safe_method(request.method):
                    submitted = request.headers.get(CSRF_HEADER_NAME)
                    if not submitted:
                        # Starlette caches the parsed form, so the handler
                        # can still read it afterwards.
                        form = await request.form()
                        submitted = form.get(CSRF_FIELD_NAME)
                    # Compared against the cookie, not against `token`:
                    # `token` falls back to a freshly minted value, which
                    # an attacker could never have echoed back but which a
                    # confused client might. No cookie means no match.
                    if not csrf_tokens_match(submitted, cookie_token):
                        response = HTMLResponse(
                            "CSRF token missing or invalid. Reload the page and try again.",
                            status_code=403,
                        )
                        _decorate(response, token, cookie_token, request, base_path)
                        return response

                response = await original(request)
                _decorate(response, token, cookie_token, request, base_path)
                return response

            return handler

    return CSRFRoute


def _decorate(
    response: Response,
    token: str,
    cookie_token: str | None,
    request: Request,
    base_path: str,
) -> None:
    """Set the token cookie (when new) and the clickjacking headers.

    The headers are unconditional: framing is a different attack from
    forgery, so the CSRF opt-out does not disable them.
    """
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    if cookie_token is None:
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            path=base_path,
            httponly=True,
            samesite="lax",
            # Secure only over TLS: a Secure cookie is not sent over plain
            # HTTP, which would break running the example on a LAN
            # address. Behind a proxy this needs X-Forwarded-Proto.
            secure=request.url.scheme == "https",
        )
