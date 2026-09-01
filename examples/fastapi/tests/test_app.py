import pytest
from fastapi.testclient import TestClient

from polyadmin.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, new_csrf_token

from main import app

client = TestClient(app)


def csrf():
    """Give the client a CSRF token and return the matching header.

    Every mutating admin route requires one (see
    docs/authentication.md). Real browsers get the pair from the cookie
    plus the meta tag base.html renders; a test supplies both halves
    itself.
    """
    token = new_csrf_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


@pytest.fixture(autouse=True)
def signed_in():
    """Sign in before each test.

    The example is behind a real login (session.py) rather than an
    authenticator hardcoded to a superuser, so every admin route
    redirects to /admin/login without a session. Going through the form
    rather than forging a cookie means these tests also cover the login
    flow itself.
    """
    response = client.post(
        "/admin/login",
        data={"identifier": "admin@example.com", "password": "polyadmin"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 303, "signing in failed; every assertion below would be vacuous"
    yield
    client.cookies.clear()


def test_unauthenticated_request_is_sent_to_the_login_page():
    client.cookies.clear()
    response = client.get("/admin/users", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/login")


def test_wrong_password_is_refused():
    client.cookies.clear()
    response = client.post(
        "/admin/login",
        data={"identifier": "admin@example.com", "password": "not it"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 401
    assert "match an account" in response.text


def _sign_in_as(email):
    client.cookies.clear()
    response = client.post(
        "/admin/login",
        data={"identifier": email, "password": "polyadmin"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 303, f"signing in as {email} failed"


# The viewer account exists to show the permission system doing
# something other than refusing everything. It previously did refuse
# everything -- SuperuserAuthorizer is all-or-nothing, so a non-superuser
# got 403 on every page including the dashboard, which made the account
# pointless and the admin look broken.
def test_non_superuser_can_read():
    _sign_in_as("viewer@example.com")
    assert client.get("/admin", follow_redirects=False).status_code == 200
    listing = client.get("/admin/users")
    assert listing.status_code == 200
    assert "admin@example.com" in listing.text


def test_non_superuser_cannot_write():
    _sign_in_as("viewer@example.com")
    response = client.post(
        "/admin/users/create",
        data={"email": "sneaky@example.com", "is_active": "on", "plan": "Pro"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 403
    # Enforced at the route, not merely hidden in the template.
    _sign_in_as("admin@example.com")
    assert "sneaky@example.com" not in client.get("/admin/users").text


def test_non_superuser_is_not_offered_controls_they_cannot_use():
    _sign_in_as("viewer@example.com")
    page = client.get("/admin/users").text
    # Guard against the vacuous version of this test: under the old
    # all-or-nothing authorizer this page was a bare 403 body, which
    # contains no Add link either.
    assert "admin@example.com" in page, "not the real list page; the assertion below would be vacuous"
    assert "/admin/users/create" not in page, "an Add control the viewer cannot use"


def test_dashboard_renders_at_admin_root():
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 200
    assert "Overview" in response.text


def test_seeded_users_appear_in_list():
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert "admin@example.com" in response.text
    assert "jane@example.com" in response.text


def test_create_user_end_to_end():
    response = client.post(
        "/admin/users/create",
        data={"email": "new-user@example.com", "is_active": "on", "plan": "Pro"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 303

    location = response.headers["location"]
    detail = client.get(location)
    assert detail.status_code == 200
    assert "new-user@example.com" in detail.text
    # The choice field round-trips: ui/select posts through a hidden
    # input, so this is the example's coverage of that widget.
    assert "Pro" in detail.text
