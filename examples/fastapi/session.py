"""A reference LoginBackend: cookie sessions over an in-memory user table.

The admin owns the login page but not the session, which is why this lives in
the example rather than the framework: where a session lives is an application
decision, and never needing a signing secret is what keeps the framework out of
key management. Swap it for whatever the app already has and the login page
keeps working.

One class implements both halves on purpose -- LoginBackend writes the session,
Authenticator reads it back, and they have to agree on the format.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from polyadmin.core.auth import Principal
from polyadmin.core.authorization import DASHBOARD_VIEW

logger = logging.getLogger("example")

SESSION_COOKIE_NAME = "admin_session"
SESSION_TTL_SECONDS = 12 * 60 * 60

# PBKDF2 parameters. 600k iterations of SHA-256 is OWASP's 2023 floor;
# it is deliberately slow, which is the point.
PBKDF2_ITERATIONS = 600_000
PBKDF2_KEY_LENGTH = 32


@dataclass
class DemoAccount:
    """One row of what would be a users table."""

    email: str
    username: str
    # Salt and hash, never the password. Derived at import time only
    # because a runnable demo has to document its own credentials; a real
    # table stores these and has never seen the plaintext.
    salt: bytes
    hash: bytes
    display_name: str
    is_superuser: bool
    locale: str


# Three accounts, not two, so the difference between a superuser and an
# ordinary signed-in user is visible in the admin, and so is a principal
# whose preferred locale the host resolver -- not the switcher cookie or
# Accept-Language -- decides.
DEMO_CREDENTIALS = [
    ("admin@example.com", "admin", "polyadmin", "Demo Admin", True, ""),
    ("viewer@example.com", "viewer", "polyadmin", "Demo Viewer", False, ""),
    ("amelie@example.com", "amelie", "polyadmin", "Amélie", True, "fr"),
]


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, PBKDF2_KEY_LENGTH)


def _session_secret() -> bytes:
    """Keys the cookie signature: from the environment when set, otherwise a fresh
    random one, so sessions do not survive a restart and are not shared across
    replicas. Right for a demo, wrong for anything else, hence the warning.
    """
    from_env = os.environ.get("ADMIN_SESSION_SECRET")
    if from_env:
        return from_env.encode()
    logger.warning(
        "ADMIN_SESSION_SECRET is unset -- using a random per-process secret, "
        "so sessions end when this process does"
    )
    return secrets.token_bytes(32)


class ReadOnlyForNonSuperusers:
    """Grants reads to anyone signed in and reserves writes for superusers.

    SuperuserAuthorizer is the obvious choice and the wrong one here: being
    all-or-nothing, it refuses a signed-in non-superuser every permission
    including dashboard.view, so the second demo account sees "Permission
    denied." everywhere and the admin looks broken rather than permissioned.
    This is the smallest rule that shows the permission system working -- as
    viewer@example.com the Add button, the row controls and the Tools page all
    disappear, because compute_permissions asks this same Authorizer which
    controls to render.
    """

    def can(self, principal: Any, permission: str, resource: Any = None) -> bool:
        if principal is None:
            return False
        if principal.is_superuser:
            return True
        if permission == DASHBOARD_VIEW:
            return True
        # "{slug}.{action}" -- see core.authorization.resource_permission.
        # Reads only; writes and the custom pages fall through.
        return permission.endswith((".view", ".list", ".export"))


class CookieSessionBackend:
    """Signs a cookie holding the account's email and an expiry. Nothing else is
    stored: the cookie is the session, which is the smallest thing that can
    honestly be called one.
    """

    def __init__(self) -> None:
        self._secret = _session_secret()
        self._accounts: dict[str, DemoAccount] = {}
        for email, username, password, display_name, is_superuser, locale in DEMO_CREDENTIALS:
            salt = secrets.token_bytes(16)
            account = DemoAccount(
                email=email,
                username=username,
                salt=salt,
                hash=_derive(password, salt),
                display_name=display_name,
                is_superuser=is_superuser,
                locale=locale,
            )
            # Indexed under both so the login page's "username or email"
            # field resolves either one to the same account.
            self._accounts[email] = account
            self._accounts[username] = account

    def verify_credentials(self, request: Any, identifier: str, password: str) -> Principal | None:
        """Answers "are these good?" and does not touch the response. Establishing
        the session is begin_session's job, which is what lets the admin refuse
        to sign someone in when the store is broken.
        """
        account = self._accounts.get(identifier.strip().lower())
        if account is None:
            # Hash anyway: returning early would make "no such account"
            # measurably faster than "wrong password", the distinction
            # LoginBackend asks implementations not to leak.
            _derive(password, b"\x00" * 16)
            return None
        if not hmac.compare_digest(_derive(password, account.salt), account.hash):
            return None
        return self._principal(account)

    def begin_session(self, request: Any, principal: Any, response: Any) -> None:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            self._sign(str(principal.id), int(time.time()) + SESSION_TTL_SECONDS),
            max_age=SESSION_TTL_SECONDS,
            path="/",
            httponly=True,
            samesite="lax",
            # Secure only over TLS: a Secure cookie is not sent over plain
            # HTTP, which would break running the example on a LAN
            # address.
            secure=request.url.scheme == "https",
        )

    def end_session(self, request: Any, response: Any) -> None:
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")

    def authenticate(self, request: Any) -> Principal | None:
        """The read side, and the reason this class implements both interfaces: it
        has to parse exactly what begin_session wrote.
        """
        subject = self._verify(request.cookies.get(SESSION_COOKIE_NAME, ""))
        if subject is None:
            return None
        account = self._accounts.get(subject)
        if account is None:
            # The signature was good but the account is gone. A valid
            # signature over a stale subject is still not an authenticated
            # request.
            return None
        return self._principal(account)

    def _principal(self, account: DemoAccount) -> Principal:
        return Principal(
            id=account.email,
            display_name=account.display_name,
            is_superuser=account.is_superuser,
            extra={"locale": account.locale},
        )

    def _sign(self, subject: str, expires_at: int) -> str:
        """Renders "<subject>|<expiry>|<mac>". The MAC covers both together, so
        neither can be edited alone: signing only the subject would let anyone
        extend their own session indefinitely.
        """
        payload = f"{subject}|{expires_at}"
        return f"{payload}|{self._mac(payload)}"

    def _verify(self, cookie: str) -> str | None:
        if not cookie:
            return None
        # Exactly three fields, or nothing: a subject containing "|" would
        # shift the expiry and MAC along and be checked against the wrong
        # values.
        parts = cookie.split("|")
        if len(parts) != 3:
            return None
        subject, expiry, mac = parts
        if not hmac.compare_digest(self._mac(f"{subject}|{expiry}"), mac):
            return None
        # Expiry is checked only after the signature: an unsigned
        # cookie's expiry field is attacker-controlled and means nothing.
        try:
            if time.time() > int(expiry):
                return None
        except ValueError:
            return None
        return subject

    def _mac(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
