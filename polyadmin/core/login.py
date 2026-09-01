"""Login: the write side of authentication.

Mirrors go-polyadmin/core/login.go.

Authenticator (auth.py) reads an existing session and answers "who is
this request?". A LoginBackend is its counterpart: it answers "are these
credentials good?" and then creates or destroys the session the
Authenticator will go on to read.

The split is deliberate, and it is what keeps this framework out of key
management. The admin owns the login *page* -- the form, the error
state, the redirect dance, the CSRF check -- because that is
presentation, and presentation is what this framework is for. It does
not own the session: it never mints a token, so it never needs a signing
secret. How a session is stored (a signed cookie, a server-side store, a
JWT, an upstream IdP) remains the host application's decision, exactly as
docs/authentication.md says identity itself does.

See examples/fastapi/session.py for a cookie-backed implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# The routes the adapters mount, relative to the admin's base path.
# Constants rather than settings: a configurable login path buys nothing
# (the page is the framework's, not the application's) and every link to
# it -- the redirect an unauthenticated request gets, the sidebar's
# sign-out button -- would have to thread the value through.
LOGIN_PATH = "/login"
LOGOUT_PATH = "/logout"

# Carries the URL an unauthenticated visitor was trying to reach, so
# signing in returns them there instead of dumping them on the dashboard.
NEXT_QUERY_PARAM = "next"


@runtime_checkable
class LoginBackend(Protocol):
    """What an application implements to turn on the admin's built-in
    login page.

    Passing one to `Admin(login_backend=...)` is the switch: with no
    backend the login routes are not mounted at all and an
    unauthenticated request is answered with 401, exactly as before this
    existed.

    `request` is untyped for the same reason it is on Authenticator --
    core must not know what a fastapi.Request is.
    """

    def verify_credentials(self, request: Any, identifier: str, password: str) -> Any:
        """Return the Principal these credentials identify, or None if
        they are not valid. Returning None is an ordinary outcome, not an
        error: the page re-renders with a message.

        Implementations must compare passwords in constant time and must
        not distinguish "no such user" from "wrong password" to the
        caller -- the admin renders one message for both, and a backend
        that leaks the difference through timing undoes that.
        """
        ...

    def begin_session(self, request: Any, principal: Any, response: Any) -> None:
        """Persist the sign-in so that the Authenticator recognises
        subsequent requests. Called only after verify_credentials has
        returned a Principal.

        `response` is the redirect the visitor is about to receive, so a
        cookie-backed implementation has something to set the cookie on.
        This is the one place the Go and Python contracts differ: Fiber's
        *fiber.Ctx is both request and response, so BeginSession there
        takes two arguments, while Starlette has no "current response"
        to reach for.

        Raise to report that the session could not be stored; the admin
        then refuses the sign-in rather than telling the visitor they are
        signed in when they are not.
        """
        ...

    def end_session(self, request: Any, response: Any) -> None:
        """Clear it. Called by the logout route, and expected to succeed
        even when there is no session to clear. Takes the outgoing
        response for the same reason begin_session does."""
        ...


def safe_next_url(next_url: str | None, base_path: str) -> str:
    """Guard the open redirect a `next` parameter opens if it is echoed
    back into a Location header unchecked.

    An attacker who can get a victim to click
    /admin/login?next=https://evil.example gets the admin's own domain to
    bounce them somewhere hostile, after a real, successful login.

    The rule is that a destination must be a path inside this admin.
    Anything else -- a different origin, a scheme-relative //host URL, a
    path outside base_path, or an empty value -- falls back to base_path
    itself. Callers use the return value directly; there is no "invalid"
    signal to forget to check.
    """
    if not next_url or not next_url.startswith("/"):
        return base_path
    # Scheme-relative ("//evil.example") is a URL, not a path, and
    # browsers treat it as one.
    if next_url[1:2] in ("/", "\\"):
        return base_path
    # A backslash anywhere is rejected rather than normalised: some
    # browsers fold it to a forward slash, so "/\evil.example" can escape
    # even though it passes the checks above.
    if "\\" in next_url:
        return base_path
    if not _is_under_base_path(next_url, base_path):
        return base_path
    return next_url


def _is_under_base_path(path: str, base_path: str) -> bool:
    """Whether path is base_path or sits beneath it.

    The boundary check matters: "/adminutes" starts with "/admin" as a
    string but is a different route entirely.
    """
    trimmed = base_path.rstrip("/")
    if trimmed in ("", "/"):
        return True
    if not path.startswith(trimmed):
        return False
    return len(path) == len(trimmed) or path[len(trimmed)] in ("/", "?")
