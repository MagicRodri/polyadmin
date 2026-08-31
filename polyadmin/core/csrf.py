"""CSRF token primitives, mirrored by go-polyadmin/core/csrf.go.

The wire names below are shared with the Go implementation and with both
adapters' templates. Changing one side without the other silently breaks
every form in the other language.
"""

from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlsplit

CSRF_COOKIE_NAME = "admin_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FIELD_NAME = "_csrf"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def new_csrf_token() -> str:
    """32 crypto-random bytes as unpadded base64url (43 characters)."""
    return secrets.token_urlsafe(32)


def is_safe_method(method: str) -> bool:
    """Whether a method is read-only per RFC 9110, and so needs no token."""
    return method.upper() in _SAFE_METHODS


def csrf_tokens_match(a: str | None, b: str | None) -> bool:
    """Constant-time compare.

    Empty on either side is always False: "no cookie" and "no submitted
    token" must fail closed rather than match each other.
    """
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)


def safe_redirect_path(referer: str | None, host: str, base_path: str, fallback: str) -> str:
    """Validate a client-supplied Referer before using it as a redirect
    target, returning `fallback` when it cannot be trusted.

    A raw Referer is attacker-controlled: without this, an action could be
    made to bounce the signed-in admin to any site on the internet. The
    return value is always a path, so the redirect can only ever land
    inside this admin.
    """
    if not referer:
        return fallback
    try:
        parsed = urlsplit(referer)
    except ValueError:
        return fallback
    # A non-empty host must be ours. This also rejects protocol-relative
    # "//evil.example.com/admin", which parses with no scheme but a
    # foreign netloc.
    if parsed.netloc and parsed.netloc != host:
        return fallback
    # Exact match, or a child path -- "/adminX" must not pass for "/admin".
    if parsed.path != base_path and not parsed.path.startswith(base_path + "/"):
        return fallback
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
