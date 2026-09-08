"""Error responses.

Every failure the admin can produce used to be a bare text body --
`HTMLResponse("Permission denied.", status_code=403)` and friends.
Someone signed into a themed admin who followed a stale link got a
white page with three words on it, no navigation, and no way back.
These render the same failures as an actual page.

Deliberately renderer-independent: the page needs the site title and
the base path and nothing else, so the handlers that never took a
Renderer and the CSRF route class can all report errors without
threading one through.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from polyadmin.fastapi.responses import is_htmx_request

FORBIDDEN = ("Permission denied", "Your account doesn't have permission to do that.")
NOT_FOUND = ("Not found", "That record doesn't exist, or it was deleted.")
UNAUTHENTICATED = ("Sign-in required", "You need to be signed in to view this page.")
CSRF_FAILED = (
    "Security check failed",
    "This page expired before the form was submitted. Reload and try again.",
)


@lru_cache(maxsize=1)
def _renderer():
    # Built once: the error page is request-independent apart from the
    # status, the message, and two strings off the Admin. Imported here
    # rather than at module scope to keep this module importable from
    # templating.py's own dependencies without a cycle.
    from polyadmin.templating import Renderer

    return Renderer()


def error_response(
    request: Request,
    admin: Any,
    base_path: str,
    status: int,
    title: str,
    message: str,
) -> HTMLResponse:
    """Render a failure as a page -- or, for an htmx request, as just the
    alert, since a whole document swapped into a table cell is nonsense.
    """
    context = {
        "site_title": getattr(admin, "site_title", "") or "PolyAdmin",
        "status": status,
        "title": title,
        "message": message,
        # No point offering the link when an unauthenticated visitor
        # cannot reach the dashboard either.
        "home_url": "" if status == 401 else base_path,
    }
    template = (
        "admin/components/error_fragment.html" if is_htmx_request(request) else "admin/error.html"
    )
    try:
        html = _renderer().render(template, context)
    except Exception:  # noqa: BLE001 -- see below
        # The error page itself failed to build. Fall back to the plain
        # body rather than returning nothing at all -- an ugly 403 beats
        # a blank 500 that hides which failure actually happened.
        return HTMLResponse(message, status_code=status)
    return HTMLResponse(html, status_code=status)


def forbidden(request: Request, admin: Any, base_path: str) -> HTMLResponse:
    return error_response(request, admin, base_path, 403, *FORBIDDEN)


def not_found(request: Request, admin: Any, base_path: str) -> HTMLResponse:
    return error_response(request, admin, base_path, 404, *NOT_FOUND)


def unauthenticated(request: Request, admin: Any, base_path: str) -> HTMLResponse:
    return error_response(request, admin, base_path, 401, *UNAUTHENTICATED)


def csrf_failure(request: Request, admin: Any, base_path: str) -> HTMLResponse:
    return error_response(request, admin, base_path, 403, *CSRF_FAILED)
