import re

import pytest
from fastapi.testclient import TestClient
from main import app

from polyadmin.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, new_csrf_token

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


def test_create_organization_persists_founded_and_balance():
    response = client.post(
        "/admin/organizations/create",
        data={"name": "Startup Co", "founded": "2020-06-15", "balance": "999.75"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 303

    location = response.headers["location"]
    detail = client.get(location)
    assert detail.status_code == 200
    # Rendered as the markup contract (Task 12): a <time datetime="...">
    # for the date and a data-value carrying the exact posted precision.
    # This exercises the real create() pipeline end to end -- Field.parse_
    # form_value (float for "decimal", raw string for "date"), the example
    # admin's own validators (organization_admin.py's _valid_founded_date/
    # _valid_balance), then its create() turning both into the model's
    # types -- not just a unit call.
    assert '<time datetime="2020-06-15" data-format="date">2020-06-15</time>' in detail.text
    assert 'data-value="999.75"' in detail.text


def test_editing_an_organization_updates_founded_and_balance():
    create = client.post(
        "/admin/organizations/create",
        data={"name": "Edit Target", "founded": "2020-06-15", "balance": "999.75"},
        follow_redirects=False,
        headers=csrf(),
    )
    location = create.headers["location"]
    pk = location.rsplit("/", 1)[-1]

    edit = client.post(
        f"/admin/organizations/{pk}/edit",
        data={"name": "Edit Target", "founded": "2021-01-02", "balance": "42.5"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert edit.status_code == 303

    detail = client.get(location)
    assert '<time datetime="2021-01-02" data-format="date">2021-01-02</time>' in detail.text
    assert 'data-value="42.5"' in detail.text


def test_create_organization_rejects_garbage_and_persists_nothing():
    response = client.post(
        "/admin/organizations/create",
        data={"name": "Bad Data Inc", "founded": "not-a-date", "balance": "not-a-number"},
        follow_redirects=False,
        headers=csrf(),
    )
    # Never silently saved as zero/None: the submission is rejected and
    # redisplayed with field errors, exactly like any other invalid field.
    assert response.status_code == 422
    assert "Enter a valid date." in response.text
    assert "Enter a valid number." in response.text
    assert "Bad Data Inc" not in client.get("/admin/organizations").text


def test_editing_an_organization_rejects_garbage_and_keeps_original_values():
    create = client.post(
        "/admin/organizations/create",
        data={"name": "Keep Me", "founded": "2018-01-01", "balance": "100"},
        follow_redirects=False,
        headers=csrf(),
    )
    location = create.headers["location"]
    pk = location.rsplit("/", 1)[-1]

    edit = client.post(
        f"/admin/organizations/{pk}/edit",
        data={"name": "Keep Me", "founded": "nope", "balance": "nope"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert edit.status_code == 422
    assert "Enter a valid date." in edit.text
    assert "Enter a valid number." in edit.text

    # The rejected update must not have touched the record. A whole-number
    # balance renders as "100", not "100.0" (see templating.py's
    # decimal_display: a float gets the shortest round-trip fixed-point
    # digits, matching Go, so this is an exact match, not a prefix check).
    detail = client.get(location)
    assert '<time datetime="2018-01-01" data-format="date">2018-01-01</time>' in detail.text
    assert 'data-value="100"' in detail.text


def test_create_organization_with_both_fields_empty_saves_successfully():
    response = client.post(
        "/admin/organizations/create",
        data={"name": "No Dates Yet", "founded": "", "balance": ""},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 303

    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "No Dates Yet" in detail.text
    # Optional and left blank: no <time> element for founded at all.
    assert "data-format=\"date\"" not in detail.text


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


_FOUNDED_INPUT = re.compile(r'name="founded"\s+value="([^"]*)"')


def _founded_form_value(body):
    """What the edit form's founded input would post back untouched."""
    match = _FOUNDED_INPUT.search(body)
    assert match, "the edit form has no founded input"
    return match.group(1)


def _create_organization(founded):
    response = client.post(
        "/admin/organizations/create",
        data={"name": "Form Target", "founded": founded, "balance": "100"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert response.status_code == 303
    return response.headers["location"]


def test_edit_form_fills_founded_with_an_iso_date():
    location = _create_organization("2019-03-01")
    assert 'value="2019-03-01"' in client.get(f"{location}/edit").text


def test_editing_without_touching_founded_keeps_it():
    location = _create_organization("2019-03-01")
    founded = _founded_form_value(client.get(f"{location}/edit").text)
    edit = client.post(
        f"{location}/edit",
        data={"name": "Form Target Renamed", "founded": founded, "balance": "100"},
        follow_redirects=False,
        headers=csrf(),
    )
    assert edit.status_code == 303
    assert '<time datetime="2019-03-01" data-format="date">2019-03-01</time>' in client.get(location).text
