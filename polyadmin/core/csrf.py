"""CSRF token primitives, mirrored by go-polyadmin/core/csrf.go.

The wire names below are shared with the Go implementation and with both
adapters' templates. Changing one side without the other silently breaks
every form in the other language.
"""

from __future__ import annotations

import hmac
import secrets

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
