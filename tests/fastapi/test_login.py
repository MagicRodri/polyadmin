"""The login page and its gate. Mirrors go-polyadmin/fiber/login_test.go."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator, DenyAllAuthenticator, Principal
from polyadmin.core.login import NEXT_QUERY_PARAM
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin

SESSION_COOKIE = "test_session"


class FakeLoginBackend:
    """A LoginBackend whose session is a single cookie holding the
    principal's id -- enough to exercise the flow end to end without
    pulling a real session implementation into the library's tests. It
    doubles as the Authenticator, which is the pairing the docs describe:
    one writes the session, the other reads it.
    """

    def __init__(self, password="correct horse"):
        self.password = password
        # Counters, so a test can tell "the page rendered" from "a
        # session was actually established".
        self.begins = 0
        self.ends = 0
        # Simulates a session store that is down.
        self.begin_error = None

    def verify_credentials(self, request, identifier, password):
        if identifier != "demo@example.com" or password != self.password:
            return None
        return Principal(id="demo", display_name="Demo Admin", is_superuser=True)

    def begin_session(self, request, principal, response):
        if self.begin_error is not None:
            raise self.begin_error
        self.begins += 1
        response.set_cookie(SESSION_COOKIE, "demo", path="/")

    def end_session(self, request, response):
        self.ends += 1
        response.delete_cookie(SESSION_COOKIE, path="/")

    def authenticate(self, request):
        if not request.cookies.get(SESSION_COOKIE):
            return None
        return Principal(id="demo", display_name="Demo Admin", is_superuser=True)


def _client(admin):
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    # follow_redirects=False: the redirect itself is what most of these
    # tests are about.
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def backend():
    return FakeLoginBackend()


@pytest.fixture
def client(backend):
    return _client(
        Admin(
            model_admins=[InMemoryUserAdmin()],
            authenticator=backend,
            login_backend=backend,
        )
    )


def _next_of(location):
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(location).query).get(NEXT_QUERY_PARAM, [""])[0]


# -- the gate -------------------------------------------------------------


def test_unauthenticated_request_redirects_to_login(client):
    response = client.get("/admin/users")
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/admin/login?")
    # The whole point of the redirect: it has to come back afterwards.
    assert _next_of(location) == "/admin/users"


# The query string is part of where they were going -- dropping it would
# return someone to page 1 of an unsorted list after signing in.
def test_login_redirect_preserves_the_query_string(client):
    response = client.get("/admin/users?page=3&sort=email")
    assert _next_of(response.headers["location"]) == "/admin/users?page=3&sort=email"


# An expired session usually surfaces mid-page, on an htmx request. A 303
# there would be followed by htmx and swapped into the page as content --
# a login form inside a table cell. HX-Redirect navigates the window.
def test_unauthenticated_htmx_request_gets_hx_redirect(client):
    response = client.get("/admin/users", headers={"HX-Request": "true"})
    assert response.headers["HX-Redirect"].startswith("/admin/login")


# Without a login_backend there is nowhere to send anyone, so the
# behaviour must be exactly what it was before login existed.
def test_without_a_login_backend_unauthenticated_is_still_401():
    client = _client(Admin(model_admins=[InMemoryUserAdmin()], authenticator=DenyAllAuthenticator()))
    assert client.get("/admin/users").status_code == 401


# ...and the login routes must not exist at all.
def test_without_a_login_backend_the_login_route_is_not_mounted():
    client = _client(Admin(model_admins=[InMemoryUserAdmin()]))
    assert client.get("/admin/login").status_code == 404


# -- the page -------------------------------------------------------------


# The login page is reachable by someone with no session -- if it were
# not, it could never be reached at all.
def test_login_page_is_publicly_reachable(client):
    response = client.get("/admin/login")
    assert response.status_code == 200
    for want in ['name="identifier"', 'type="password"', 'name="_csrf"', "Welcome back"]:
        assert want in response.text, want


# It is the one page outside the admin shell: there is no principal yet,
# so a sidebar listing resources would be both impossible to build and a
# lie about what the visitor can reach.
def test_login_page_renders_without_the_admin_shell(client):
    page = client.get("/admin/login").text
    for unwanted in ("sidebarOpen", "breadcrumb", "Breadcrumb"):
        assert unwanted not in page, unwanted
    # But it must still carry the theme, or signing in flashes a light
    # page at someone who chose dark.
    assert "polyadmin-theme" in page


# The dropped login-04 controls: each would be a dead end.
def test_login_page_omits_controls_with_no_route_behind_them(client):
    page = client.get("/admin/login").text
    for unwanted in ("Forgot your password", "Sign up", "Login with Google", "Or continue with"):
        assert unwanted not in page, unwanted


# -- signing in -----------------------------------------------------------


def test_valid_credentials_begin_a_session_and_return_to_next(client, backend):
    response = client.post(
        "/admin/login?next=%2Fadmin%2Fusers",
        data={"identifier": "demo@example.com", "password": "correct horse"},
        headers=csrf(client),
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"
    assert backend.begins == 1


def test_invalid_credentials_do_not_begin_a_session(client, backend):
    response = client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "wrong"},
        headers=csrf(client),
    )
    assert response.status_code == 401
    assert backend.begins == 0
    assert "match an account" in response.text


# A wrong password must not cost the email as well.
def test_failed_sign_in_echoes_the_identifier_back(client):
    response = client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "wrong"},
        headers=csrf(client),
    )
    assert 'value="demo@example.com"' in response.text


# One message for both, or the form is an account enumerator.
def test_unknown_user_and_wrong_password_are_indistinguishable(client):
    def alert_of(text):
        start = text.index('role="alert"')
        return text[start : text.index("</div>", start)]

    wrong_password = client.post(
        "/admin/login", data={"identifier": "demo@example.com", "password": "wrong"}, headers=csrf(client)
    ).text
    no_such_user = client.post(
        "/admin/login", data={"identifier": "nobody@example.com", "password": "wrong"}, headers=csrf(client)
    ).text
    # Compare the rendered alert, not the whole page -- the echoed
    # identifier differs by construction.
    assert alert_of(wrong_password) == alert_of(no_such_user)


# Credentials good, session store down: the visitor is not signed in and
# must not be told they are.
def test_session_failure_does_not_sign_anyone_in(client, backend):
    backend.begin_error = RuntimeError("session store unavailable")
    response = client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "correct horse"},
        headers=csrf(client),
    )
    assert response.status_code == 500
    assert "location" not in response.headers


# The open-redirect guard, exercised through the actual route rather than
# only against safe_next_url directly.
def test_sign_in_refuses_to_redirect_off_site(client):
    response = client.post(
        "/admin/login?next=https%3A%2F%2Fevil.example",
        data={"identifier": "demo@example.com", "password": "correct horse"},
        headers=csrf(client),
    )
    assert response.headers["location"] == "/admin"


# Nothing to do here for someone who already has a session.
def test_login_page_redirects_an_already_signed_in_visitor(client):
    client.cookies.set(SESSION_COOKIE, "demo")
    assert client.get("/admin/login").status_code == 303


# -- signing out ----------------------------------------------------------


# The control has to exist somewhere, or the only way out of the admin is
# to clear cookies by hand.
def test_sidebar_offers_sign_out_when_a_login_backend_is_configured(client):
    client.cookies.set(SESSION_COOKIE, "demo")
    page = client.get("/admin/users").text
    assert "Sign out" in page
    # A form, not a link: see the template's note on GET logouts.
    assert '<form method="post" action="/admin/logout">' in page


# Without a backend there is no logout route, so the control would be a
# dead button.
def test_sidebar_omits_sign_out_without_a_login_backend():
    client = _client(
        Admin(
            model_admins=[InMemoryUserAdmin()],
            authenticator=AllowAllAuthenticator(Principal(id="demo", display_name="Demo")),
        )
    )
    assert "Sign out" not in client.get("/admin/users").text


def test_logout_ends_the_session_and_says_so(client, backend):
    client.cookies.set(SESSION_COOKIE, "demo")
    response = client.post("/admin/logout", headers=csrf(client))
    assert backend.ends == 1
    assert response.headers["location"].startswith("/admin/login")
    # The session must actually be cleared, not merely redirected away
    # from. Asserted on the Set-Cookie header rather than on the client's
    # jar: a cookie put there by cookies.set() has no domain, so httpx
    # will not match the deletion against it -- a test artifact, not
    # something the browser shares.
    cleared = [c for c in response.headers.get_list("set-cookie") if c.startswith(SESSION_COOKIE + "=")]
    assert cleared, "logout sent no Set-Cookie for the session"
    assert "Max-Age=0" in cleared[0] or "expires=" in cleared[0].lower()


def test_logout_lands_on_a_page_confirming_it(client):
    assert "signed out" in client.get("/admin/login?signedout=1").text


# A logout reachable by GET is one any <img src> on the internet can fire
# at a signed-in admin.
def test_logout_rejects_get(client, backend):
    assert client.get("/admin/logout").status_code == 405
    assert backend.ends == 0
