"""The login page's handlers. Mirrors go-polyadmin/fiber/login.go."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from polyadmin.core.admin import Admin
from polyadmin.core.login import NEXT_QUERY_PARAM, safe_next_url
from polyadmin.fastapi.responses import redirect
from polyadmin.templating import Renderer

logger = logging.getLogger("polyadmin")

# The two messages the login page can show. INVALID_CREDENTIALS is
# deliberately one message for both "no such user" and "wrong password":
# telling them apart turns the form into an account enumerator.
# core.login.LoginBackend asks implementations not to distinguish them
# either, for the same reason.
INVALID_CREDENTIALS = "That email and password don't match an account."
SIGNED_OUT = "You have been signed out."
SESSION_FAILED = "Sign-in could not be completed. Please try again."


def build_login_handlers(admin: Admin, renderer: Renderer, base_path: str):
    """The GET and POST for the login page.

    These are two of only three routes in a mounted admin that run
    without authenticating (the third is logout), since requiring a
    session to reach the page that creates one is a loop.
    """

    def _page(request: Request, *, identifier: str = "", error: str = "", notice: str = "", status: int = 200) -> HTMLResponse:
        html = renderer.render_login(
            admin,
            csrf_token=request.state.csrf_token,
            identifier=identifier,
            error=error,
            notice=notice,
        )
        return HTMLResponse(html, status_code=status)

    async def login_get(request: Request) -> Response:
        # Already signed in: nothing here to do, so honour ?next= and
        # send them on rather than showing a form they would have to
        # pointlessly fill in.
        if admin.authenticator is not None and admin.authenticator.authenticate(request) is not None:
            return RedirectResponse(
                safe_next_url(request.query_params.get(NEXT_QUERY_PARAM), base_path), status_code=303
            )
        notice = SIGNED_OUT if request.query_params.get("signedout") == "1" else ""
        return _page(request, notice=notice)

    async def login_post(request: Request) -> Response:
        # CSRF is already enforced -- the router's route_class covers
        # every route, this one included, and the GET above is what mints
        # the cookie the form echoes back.
        form = await request.form()
        identifier = str(form.get("identifier") or "")
        password = str(form.get("password") or "")
        next_url = safe_next_url(request.query_params.get(NEXT_QUERY_PARAM), base_path)

        principal = admin.login_backend.verify_credentials(request, identifier, password)
        if principal is None:
            # 401, not 200: a failed sign-in is a failed sign-in, and the
            # status is what a log or a rate limiter in front of this
            # reads. The body is still the form.
            return _page(request, identifier=identifier, error=INVALID_CREDENTIALS, status=401)

        response = RedirectResponse(next_url, status_code=303)
        try:
            # The response is handed over so the backend can set a cookie
            # on it. This is the one place the two implementations'
            # signatures differ: Fiber's ctx is both request and
            # response, while Starlette has no "current response" to
            # reach for -- see core/login.py.
            admin.login_backend.begin_session(request, principal, response)
        except Exception as exc:
            # The credentials were right but the session could not be
            # stored, so the visitor is not signed in and must not be
            # told they are. Logged for the operator, generic on screen.
            logger.warning("begin_session failed for %s: %s", principal.id, exc)
            return _page(request, identifier=identifier, error=SESSION_FAILED, status=500)
        return response

    return login_get, login_post


def build_logout_handler(admin: Admin, base_path: str):
    """POST-only (see the route table): a logout reachable by GET is one
    any <img src> on the internet can trigger."""

    async def logout(request: Request) -> Response:
        response = redirect(request, f"{base_path}/login?signedout=1")
        try:
            admin.login_backend.end_session(request, response)
        except Exception as exc:
            # Nothing useful to offer the visitor here: they asked to
            # leave, and the most likely reason this failed is that there
            # was nothing to clear.
            logger.warning("end_session failed: %s", exc)
        return response

    return logout
