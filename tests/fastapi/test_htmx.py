from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.filter import BooleanFilter
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin

HTMX_HEADERS = {"HX-Request": "true"}


class FilterableUserAdmin(InMemoryUserAdmin):
    filters = [BooleanFilter("is_active")]


def make_client(user_admin_cls=InMemoryUserAdmin):
    user_admin = user_admin_cls()
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_list_search_filters_rows():
    client, user_admin = make_client()
    user_admin.create({"email": "john@example.com"})
    user_admin.create({"email": "mary@example.com"})

    response = client.get("/admin/users?search=john")
    assert "john@example.com" in response.text
    assert "mary@example.com" not in response.text


def test_list_filter_bracket_syntax():
    client, user_admin = make_client(FilterableUserAdmin)
    user_admin.create({"email": "active@example.com", "is_active": True})
    user_admin.create({"email": "inactive@example.com", "is_active": False})

    response = client.get("/admin/users?filter[is_active]=true")
    assert "active@example.com" in response.text
    assert "inactive@example.com" not in response.text


def test_list_sort():
    client, user_admin = make_client()
    user_admin.create({"email": "bbb@example.com"})
    user_admin.create({"email": "aaa@example.com"})

    response = client.get("/admin/users?sort=email")
    assert response.text.index("aaa@example.com") < response.text.index("bbb@example.com")


def test_htmx_list_request_returns_fragment_not_full_page():
    client, user_admin = make_client()
    user_admin.create({"email": "john@example.com"})

    response = client.get("/admin/users", headers=HTMX_HEADERS)
    assert response.status_code == 200
    assert "<html" not in response.text
    assert 'id="resource-list"' in response.text
    assert "john@example.com" in response.text


def test_htmx_delete_removes_row_without_redirect():
    client, user_admin = make_client()
    user = user_admin.create({"email": "john@example.com"})

    response = client.request("DELETE", f"/admin/users/{user.id}/delete", headers=HTMX_HEADERS)
    assert response.status_code == 200
    assert response.text == ""
    assert user_admin.get_queryset() == []


def test_htmx_create_post_returns_hx_redirect_header():
    client, user_admin = make_client()
    response = client.post(
        "/admin/users/create",
        data={"email": "new@example.com"},
        headers=HTMX_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == f"/admin/users/{user_admin.get_queryset()[0].id}"


def test_htmx_create_post_invalid_returns_form_fragment_only():
    client, _ = make_client()
    response = client.post("/admin/users/create", data={"email": ""}, headers=HTMX_HEADERS)
    assert response.status_code == 422
    assert "<html" not in response.text
    assert 'id="resource-form"' in response.text
    assert "is required" in response.text


def test_flash_message_shown_after_create_redirect():
    client, _ = make_client()
    create = client.post("/admin/users/create", data={"email": "new@example.com"}, follow_redirects=False)
    location = create.headers["location"]

    detail = client.get(location)
    assert "User created." in detail.text


def test_flash_message_only_shown_once():
    client, _ = make_client()
    create = client.post("/admin/users/create", data={"email": "new@example.com"}, follow_redirects=False)
    location = create.headers["location"]

    client.get(location)
    second_visit = client.get(location)
    assert "User created." not in second_visit.text
