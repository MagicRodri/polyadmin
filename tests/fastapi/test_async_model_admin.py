import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


class AsyncUserAdmin(InMemoryUserAdmin):
    """Every CRUD hook is a coroutine function -- the shape an HTTP-backed
    ModelAdmin (e.g. one calling httpx.AsyncClient) actually takes."""

    async def get_object(self, pk):
        await asyncio.sleep(0)
        return super().get_object(pk)

    async def create(self, data):
        await asyncio.sleep(0)
        return super().create(data)

    async def update(self, obj, data):
        await asyncio.sleep(0)
        return super().update(obj, data)

    async def delete(self, obj):
        await asyncio.sleep(0)
        super().delete(obj)


def async_client():
    user_admin = AsyncUserAdmin()
    admin = Admin(model_admins=[user_admin], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_detail_view_awaits_async_get_object():
    client, user_admin = async_client()
    user = asyncio.run(user_admin.create({"email": "john@example.com"}))
    response = client.get(f"/admin/users/{user.id}")
    assert response.status_code == 200
    assert "john@example.com" in response.text


def test_create_post_awaits_async_create():
    client, user_admin = async_client()
    response = client.post(
        "/admin/users/create", data={"email": "new@example.com"}, headers=csrf(client), follow_redirects=False
    )
    assert response.status_code in (302, 303)
    assert any(u.email == "new@example.com" for u in user_admin._store.values())


def test_edit_post_awaits_async_get_object_and_async_update():
    client, user_admin = async_client()
    user = asyncio.run(user_admin.create({"email": "old@example.com"}))
    response = client.post(
        f"/admin/users/{user.id}/edit", data={"email": "changed@example.com"}, headers=csrf(client), follow_redirects=False
    )
    assert response.status_code in (302, 303)
    assert asyncio.run(user_admin.get_object(user.id)) is not None
    assert user.email == "changed@example.com"


def test_delete_post_awaits_async_get_object_and_async_delete():
    client, user_admin = async_client()
    user = asyncio.run(user_admin.create({"email": "gone@example.com"}))
    response = client.request("DELETE", f"/admin/users/{user.id}/delete", headers=csrf(client))
    assert response.status_code == 200
    assert asyncio.run(user_admin.get_object(user.id)) is None


class AsyncListPageUserAdmin(InMemoryUserAdmin):
    async def list_page(self, list_request):
        await asyncio.sleep(0)
        objects = list(self._store.values())
        return objects, len(objects)


def test_list_view_awaits_an_async_list_page():
    user_admin = AsyncListPageUserAdmin()
    user_admin.create({"email": "async-list@example.com"})
    admin = Admin(model_admins=[user_admin], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    response = client.get("/admin/users")
    assert response.status_code == 200
    assert "async-list@example.com" in response.text


def test_bulk_action_select_all_awaits_an_async_list_page():
    user_admin = AsyncListPageUserAdmin()
    user_admin.create({"email": "a@example.com"})
    user_admin.create({"email": "b@example.com"})
    admin = Admin(model_admins=[user_admin], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    response = client.post(
        "/admin/users/actions/delete_selected",
        data={"_select_all": "1"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert len(user_admin._store) == 0
