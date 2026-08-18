"""HTMX-aware response helpers."""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

_FLASH_COOKIE = "admin_messages"


def is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def set_flash(response: Response, level: str, text: str) -> None:
    response.set_cookie(
        _FLASH_COOKIE,
        json.dumps([{"level": level, "text": text}]),
        max_age=10,
        httponly=True,
        samesite="lax",
    )


def pop_flash(request: Request) -> list[dict[str, Any]]:
    """Read pending flash messages. Does not clear the cookie itself --
    callers should call `clear_flash` on whichever response they end up
    returning, once they know they've consumed the messages.
    """
    raw = request.cookies.get(_FLASH_COOKIE)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


def clear_flash(response: Response) -> None:
    response.delete_cookie(_FLASH_COOKIE)


def redirect(request: Request, url: str) -> Response:
    """Redirect that works for both a normal browser navigation and an
    HTMX request: a plain 303 in the former case, an `HX-Redirect`
    response in the latter -- htmx otherwise treats a redirected AJAX
    response as content to swap in, not a page navigation.
    """
    if is_htmx_request(request):
        response = HTMLResponse("", status_code=200)
        response.headers["HX-Redirect"] = url
        return response
    return RedirectResponse(url, status_code=303)
