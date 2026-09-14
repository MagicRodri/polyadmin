"""Login: the write side of authentication.

Authenticator (auth.py) answers "who is this request?"; a LoginBackend answers
"are these credentials good?" and creates or destroys the session the
Authenticator reads.

The split keeps the framework out of key management. It owns the login page --
form, error state, redirect, CSRF -- because that is presentation. It never
mints a token, so it never needs a signing secret, and how a session is stored
stays the application's decision. See examples/fastapi/session.py.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# The routes the adapters mount, relative to the base path. Constants, not
# settings: the page is the framework's, and every link to it would
# otherwise have to thread the value through.
LOGIN_PATH = "/login"
LOGOUT_PATH = "/logout"
LOCALE_PATH = "/locale"

# Carries the URL an unauthenticated visitor was trying to reach, so
# signing in returns them there instead of dumping them on the dashboard.
NEXT_QUERY_PARAM = "next"


@runtime_checkable
class LoginBackend(Protocol):
    """What an application implements to turn on the admin's built-in login page.

    Passing one to `Admin(login_backend=...)` is the switch: without it the
    login routes are never mounted and an unauthenticated request gets a 401.
    `request` is untyped because core must not know what a fastapi.Request is.
    """

    def verify_credentials(self, request: Any, identifier: str, password: str) -> Any:
        """Return the Principal these credentials identify, or None if they are
        not valid. None is an ordinary outcome, not an error.

        Implementations must compare in constant time and must not distinguish
        "no such user" from "wrong password": the admin renders one message for
        both, and a backend leaking the difference through timing undoes that.
        """
        ...

    def begin_session(self, request: Any, principal: Any, response: Any) -> None:
        """Persist the sign-in so the Authenticator recognises subsequent
        requests. Called only after verify_credentials returned a Principal.

        `response` is the redirect the visitor is about to receive, so a
        cookie-backed implementation has something to set the cookie on. This
        is the one place the Go and Python contracts differ: a *fiber.Ctx is
        both request and response, while Starlette has no current response to
        reach for.

        Raise to report that the session could not be stored; the admin then
        refuses the sign-in rather than telling the visitor they are signed in
        when they are not.
        """
        ...

    def end_session(self, request: Any, response: Any) -> None:
        """Clear it. Called by the logout route, and expected to succeed even when
        there is no session to clear.
        """
        ...


def safe_next_url(next_url: str | None, base_path: str) -> str:
    """Guard the open redirect a `next` parameter opens if echoed into a Location
    header unchecked: ?next=https://evil.example would have the admin's own
    domain bounce the visitor somewhere hostile after a real login.

    A destination must be a path inside this admin; anything else falls back to
    base_path. Callers use the return value directly, so there is no "invalid"
    signal to forget to check.
    """
    if not next_url or not next_url.startswith("/"):
        return base_path
    # Scheme-relative ("//evil.example") is a URL, not a path, and
    # browsers treat it as one.
    if next_url[1:2] in ("/", "\\"):
        return base_path
    # A backslash anywhere is rejected rather than normalised: some
    # browsers fold it to a forward slash, so "/\evil.example" escapes the
    # checks above.
    if "\\" in next_url:
        return base_path
    if not _is_under_base_path(next_url, base_path):
        return base_path
    return next_url


def _is_under_base_path(path: str, base_path: str) -> bool:
    """Whether path is base_path or sits beneath it. The boundary check matters:
    "/adminutes" starts with "/admin" as a string but is a different route.
    """
    trimmed = base_path.rstrip("/")
    if trimmed in ("", "/"):
        return True
    if not path.startswith(trimmed):
        return False
    return len(path) == len(trimmed) or path[len(trimmed)] in ("/", "?")
