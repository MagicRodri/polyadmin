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
