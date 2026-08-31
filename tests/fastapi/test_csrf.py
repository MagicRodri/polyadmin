from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FIELD_NAME,
    CSRF_HEADER_NAME,
    new_csrf_token,
)
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


def make_client(**admin_kwargs):
    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin], **admin_kwargs)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_get_mints_a_token_cookie():
    client, _ = make_client()
    response = client.get("/admin/users")
    assert len(response.cookies[CSRF_COOKIE_NAME]) == 43


def test_token_cookie_is_httponly():
    # The token is rendered into a meta tag for scripts, which is what
    # lets the cookie stay HttpOnly -- so this is a real guarantee, not
    # an accident.
    client, _ = make_client()
    response = client.get("/admin/users")
    set_cookie = response.headers["set-cookie"]
    assert CSRF_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie


def test_unsafe_request_without_a_token_is_rejected():
    client, _ = make_client()
    response = client.post("/admin/users/create", data={"email": "a@example.com"})
    assert response.status_code == 403


def test_unsafe_request_with_a_mismatched_token_is_rejected():
    client, _ = make_client()
    client.cookies.set(CSRF_COOKIE_NAME, new_csrf_token())
    response = client.post(
        "/admin/users/create",
        data={"email": "a@example.com"},
        headers={CSRF_HEADER_NAME: new_csrf_token()},
    )
    assert response.status_code == 403


def test_unsafe_request_accepts_the_token_in_the_form_field():
    client, _ = make_client()
    token = new_csrf_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    response = client.post(
        "/admin/users/create",
        data={"email": "a@example.com", CSRF_FIELD_NAME: token},
    )
    assert response.status_code != 403


def test_bodyless_delete_accepts_the_token_in_the_header():
    client, user_admin = make_client()
    user = user_admin.create({"email": "a@example.com"})
    token = new_csrf_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    response = client.delete(
        f"/admin/users/{user.id}/delete", headers={CSRF_HEADER_NAME: token}
    )
    assert response.status_code != 403


def test_bodyless_delete_without_the_header_is_rejected():
    client, user_admin = make_client()
    user = user_admin.create({"email": "a@example.com"})
    response = client.delete(f"/admin/users/{user.id}/delete")
    assert response.status_code == 403


def test_clickjacking_headers_are_set():
    client, _ = make_client()
    response = client.get("/admin/users")
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_csrf_can_be_disabled():
    client, _ = make_client(disable_csrf=True)
    response = client.post("/admin/users/create", data={"email": "a@example.com"})
    assert response.status_code != 403
    # The cookie is still minted, so templates are unchanged by the opt-out.
    assert CSRF_COOKIE_NAME in response.cookies or CSRF_COOKIE_NAME in client.cookies
    # And the frame headers are not part of the opt-out.
    assert response.headers["x-frame-options"] == "DENY"
