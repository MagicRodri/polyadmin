"""The login page and its gate."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator, DenyAllAuthenticator, Principal
from polyadmin.core.login import NEXT_QUERY_PARAM
from polyadmin.fastapi.router import create_router
from polyadmin.ui import ui
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
        if identifier not in ("demo@example.com", "demo") or password != self.password:
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


def test_unauthenticated_request_redirects_to_login(client):
    response = client.get("/admin/users")
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/admin/login?")
    assert _next_of(location) == "/admin/users"


def test_login_redirect_preserves_the_query_string(client):
    response = client.get("/admin/users?page=3&sort=email")
    assert _next_of(response.headers["location"]) == "/admin/users?page=3&sort=email"


def test_unauthenticated_htmx_request_gets_hx_redirect(client):
    response = client.get("/admin/users", headers={"HX-Request": "true"})
    assert response.headers["HX-Redirect"].startswith("/admin/login")


def test_without_a_login_backend_unauthenticated_is_still_401():
    client = _client(Admin(model_admins=[InMemoryUserAdmin()], authenticator=DenyAllAuthenticator()))
    assert client.get("/admin/users").status_code == 401


def test_without_a_login_backend_the_login_route_is_not_mounted():
    client = _client(Admin(model_admins=[InMemoryUserAdmin()]))
    assert client.get("/admin/login").status_code == 404


def test_login_page_is_publicly_reachable(client):
    response = client.get("/admin/login")
    assert response.status_code == 200
    for want in ['name="identifier"', 'type="password"', 'name="_csrf"', "Welcome back"]:
        assert want in response.text, want


def test_login_identifier_field_accepts_plain_text(client):
    page = client.get("/admin/login").text
    assert 'type="email"' not in page, "identifier input rejects a plain username before it reaches the server"
    assert "Username or email" in page


def test_login_accepts_a_username_not_only_an_email(client, backend):
    response = client.post(
        "/admin/login?next=%2Fadmin%2Fusers",
        data={"identifier": "demo", "password": "correct horse"},
        headers=csrf(client),
    )
    assert response.status_code == 303
    assert backend.begins == 1


def test_login_page_renders_without_the_admin_shell(client):
    page = client.get("/admin/login").text
    for unwanted in ("sidebarOpen", "breadcrumb", "Breadcrumb"):
        assert unwanted not in page, unwanted
    # But it must still carry the theme, or signing in flashes a light
    # page at someone who chose dark.
    assert "polyadmin-theme" in page


def test_login_page_omits_controls_with_no_route_behind_them(client):
    page = client.get("/admin/login").text
    for unwanted in ("Forgot your password", "Sign up", "Login with Google", "Or continue with"):
        assert unwanted not in page, unwanted


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


def test_failed_sign_in_echoes_the_identifier_back(client):
    response = client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "wrong"},
        headers=csrf(client),
    )
    assert 'value="demo@example.com"' in response.text


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


def test_session_failure_does_not_sign_anyone_in(client, backend):
    backend.begin_error = RuntimeError("session store unavailable")
    response = client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "correct horse"},
        headers=csrf(client),
    )
    assert response.status_code == 500
    assert "location" not in response.headers


def test_sign_in_refuses_to_redirect_off_site(client):
    response = client.post(
        "/admin/login?next=https%3A%2F%2Fevil.example",
        data={"identifier": "demo@example.com", "password": "correct horse"},
        headers=csrf(client),
    )
    assert response.headers["location"] == "/admin"


def test_login_page_redirects_an_already_signed_in_visitor(client):
    client.cookies.set(SESSION_COOKIE, "demo")
    assert client.get("/admin/login").status_code == 303


def test_sidebar_offers_sign_out_when_a_login_backend_is_configured(client):
    client.cookies.set(SESSION_COOKIE, "demo")
    page = client.get("/admin/users").text
    assert "Sign out" in page
    # A form, not a link: see the template's note on GET logouts.
    assert '<form method="post" action="/admin/logout">' in page


def _sidebar_footer(page):
    """The sidebar's footer region, bounded at the rail that follows it."""
    footer = page[page.index(ui("sidebar", "footer")) :]
    return footer[: footer.index('aria-label="Toggle sidebar"')]


def test_the_user_menu_holds_actions_only(client):
    """The trigger the menu opens from sits directly beside it and
    already shows who you are, so an identity header inside the menu
    told the reader nothing new."""
    client.cookies.set(SESSION_COOKIE, "demo")
    footer = _sidebar_footer(client.get("/admin/users").text)

    assert "Sign out" in footer, "no sign-out in the footer; the assertions below would be vacuous"
    assert footer.count("Demo Admin") == 1, "the signed-in name is repeated in the menu"
    assert footer.count("Superuser") == 1, "the signed-in role is repeated in the menu"
    assert ui("dropdown", "label") not in footer, "the user menu still carries an identity header"


def test_with_nothing_to_sign_out_of_the_footer_opens_nothing():
    """With no login backend the menu would hold no items at all, and a
    trigger that opens an empty box is a dead end."""
    admin = Admin(
        model_admins=[InMemoryUserAdmin()],
        authenticator=AllowAllAuthenticator(Principal(id="demo", display_name="Demo")),
    )
    footer = _sidebar_footer(_client(admin).get("/admin/users").text)
    assert "Demo" in footer, "the footer does not name the principal"
    assert 'aria-haspopup="menu"' not in footer, "the footer still opens a menu with nothing in it"


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


def test_logout_rejects_get(client, backend):
    assert client.get("/admin/logout").status_code == 405
    assert backend.ends == 0


class AsyncFakeLoginBackend:
    """Every LoginBackend method is a coroutine function -- the shape a
    real database- or HTTP-backed login (e.g. checking credentials
    against an async ORM session) actually takes."""

    def __init__(self, password="correct horse"):
        self.password = password
        self.begins = 0
        self.ends = 0

    async def verify_credentials(self, request, identifier, password):
        await asyncio.sleep(0)
        if identifier != "demo@example.com" or password != self.password:
            return None
        return Principal(id="demo", display_name="Demo Admin", is_superuser=True)

    async def begin_session(self, request, principal, response):
        await asyncio.sleep(0)
        self.begins += 1
        response.set_cookie(SESSION_COOKIE, "demo", path="/")

    async def end_session(self, request, response):
        await asyncio.sleep(0)
        self.ends += 1
        response.delete_cookie(SESSION_COOKIE, path="/")

    def authenticate(self, request):
        if not request.cookies.get(SESSION_COOKIE):
            return None
        return Principal(id="demo", display_name="Demo Admin", is_superuser=True)


def _async_backend_client():
    backend = AsyncFakeLoginBackend()
    return _client(
        Admin(model_admins=[InMemoryUserAdmin()], authenticator=backend, login_backend=backend)
    ), backend


def test_async_verify_credentials_and_begin_session_are_awaited():
    client, backend = _async_backend_client()
    response = client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "correct horse"},
        headers=csrf(client),
    )
    assert response.status_code == 303
    assert backend.begins == 1


def test_async_verify_credentials_rejects_bad_password():
    client, backend = _async_backend_client()
    response = client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "wrong"},
        headers=csrf(client),
    )
    assert response.status_code == 401
    assert backend.begins == 0


def test_async_end_session_is_awaited_on_logout():
    client, backend = _async_backend_client()
    client.post(
        "/admin/login",
        data={"identifier": "demo@example.com", "password": "correct horse"},
        headers=csrf(client),
    )
    client.post("/admin/logout", headers=csrf(client))
    assert backend.ends == 1
