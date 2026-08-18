from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


def make_client():
    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_index_redirects_to_first_resource():
    client, _ = make_client()
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code in (302, 303, 307, 308)
    assert response.headers["location"] == "/admin/users"


def test_list_view_renders_html():
    client, user_admin = make_client()
    user_admin.create({"email": "john@example.com"})
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert "john@example.com" in response.text


def test_list_view_paginates():
    client, user_admin = make_client()
    for i in range(15):
        user_admin.create({"email": f"user{i}@example.com"})
    response = client.get("/admin/users?page=2&page_size=10")
    assert response.status_code == 200
    assert "2 / 2" in response.text
    assert "Showing" in response.text
    assert ">11</span>" in response.text
    assert ">15</span> results" in response.text


def test_create_get_renders_empty_form():
    client, _ = make_client()
    response = client.get("/admin/users/create")
    assert response.status_code == 200
    assert ">New</span>" in response.text


def test_create_post_redirects_to_detail():
    client, user_admin = make_client()
    response = client.post(
        "/admin/users/create",
        data={"email": "new@example.com", "is_active": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    users = user_admin.get_queryset()
    assert len(users) == 1
    assert users[0].email == "new@example.com"
    assert users[0].is_active is True
    assert response.headers["location"] == f"/admin/users/{users[0].id}"


def test_create_post_without_checkbox_is_false():
    client, user_admin = make_client()
    client.post("/admin/users/create", data={"email": "new@example.com"}, follow_redirects=False)
    assert user_admin.get_queryset()[0].is_active is False


def test_create_post_invalid_rerenders_form_with_errors():
    client, user_admin = make_client()
    response = client.post("/admin/users/create", data={"email": ""})
    assert response.status_code == 422
    assert "is required" in response.text
    assert user_admin.get_queryset() == []


def test_detail_view():
    client, user_admin = make_client()
    user = user_admin.create({"email": "john@example.com"})
    response = client.get(f"/admin/users/{user.id}")
    assert response.status_code == 200
    assert "john@example.com" in response.text


def test_detail_view_missing_is_404():
    client, _ = make_client()
    response = client.get("/admin/users/999")
    assert response.status_code == 404


def test_edit_get_prefills_form():
    client, user_admin = make_client()
    user = user_admin.create({"email": "john@example.com"})
    response = client.get(f"/admin/users/{user.id}/edit")
    assert response.status_code == 200
    assert 'value="john@example.com"' in response.text


def test_edit_post_updates_and_redirects():
    client, user_admin = make_client()
    user = user_admin.create({"email": "john@example.com"})
    response = client.post(
        f"/admin/users/{user.id}/edit", data={"email": "updated@example.com"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert user.email == "updated@example.com"


def test_edit_post_invalid_rerenders_form_with_errors():
    client, user_admin = make_client()
    user = user_admin.create({"email": "john@example.com"})
    response = client.post(f"/admin/users/{user.id}/edit", data={"email": ""})
    assert response.status_code == 422
    assert "is required" in response.text
    assert user.email == "john@example.com"  # unchanged


def test_delete_get_renders_confirmation():
    client, user_admin = make_client()
    user = user_admin.create({"email": "john@example.com"})
    response = client.get(f"/admin/users/{user.id}/delete")
    assert response.status_code == 200
    assert "Are you sure" in response.text


def test_delete_post_removes_and_redirects_to_list():
    client, user_admin = make_client()
    user = user_admin.create({"email": "john@example.com"})
    response = client.post(f"/admin/users/{user.id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"
    assert user_admin.get_queryset() == []


def test_disabled_operations_are_not_routed():
    class ReadOnlyUserAdmin(InMemoryUserAdmin):
        can_create = False
        can_update = False
        can_delete = False

    admin = Admin(model_admins=[ReadOnlyUserAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    # "create"/"1/delete" aren't distinct routes here -- can_create=False
    # means there's no dedicated POST /users/create route, so it falls
    # through to whatever *does* match that path.
    assert client.get("/admin/users/create").status_code == 404  # matches GET /{pk}, "create" isn't a real pk
    assert client.post("/admin/users/create", data={}).status_code == 405  # path matches /{pk}, but only GET is registered
    assert client.get("/admin/users/1/edit").status_code == 404  # no route has this shape at all
    assert client.post("/admin/users/1/delete").status_code == 404  # no route has this shape at all


def test_registered_page_route_is_mounted():
    from fastapi.responses import PlainTextResponse

    async def handler(ctx):
        return PlainTextResponse("broadcast page")

    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin])
    admin.route("/tools/broadcast", handler)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    response = client.get("/admin/tools/broadcast")
    assert response.status_code == 200
    assert response.text == "broadcast page"
