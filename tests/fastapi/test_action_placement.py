"""The list and detail pages offer the actions their placement allows."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.action import Action
from polyadmin.core.admin import Admin
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


def _noop(model_admin, objects, principal):
    return None


def make_client(**attrs):
    ma = type("Users", (InMemoryUserAdmin,), attrs)()
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[ma]), base_path="/admin"), prefix="/admin")
    return TestClient(app), ma


def detail_page(client, ma):
    user = ma.create({"email": "a@example.com"})
    return client.get(f"/admin/users/{user.id}").text


def test_detail_page_never_offers_delete_selected():
    client, ma = make_client()
    page = detail_page(client, ma)
    assert "actions/delete_selected" not in page
    assert "Delete selected" not in page


def test_list_page_offers_delete_selected_and_list_actions_but_not_detail_only_ones():
    client, _ = make_client(
        actions=[Action("ping", _noop, label="Ping all"), Action("sync", _noop, label="Detail sync", where="detail")]
    )
    page = client.get("/admin/users").text
    assert "Delete selected" in page
    assert "Ping all" in page
    assert "Detail sync" not in page


def test_detail_page_offers_actions_placed_on_it():
    client, ma = make_client(
        actions=[Action("ping", _noop), Action("sync", _noop, where="detail"), Action("bulk", _noop, where="list")]
    )
    page = detail_page(client, ma)
    assert "actions/ping" in page
    assert "actions/sync" in page
    assert "actions/bulk" not in page


def test_detail_actions_allowlist_limits_the_detail_page():
    client, ma = make_client(actions=[Action("ping", _noop), Action("sync", _noop)], detail_actions=["sync"])
    page = detail_page(client, ma)
    assert "actions/sync" in page
    assert "actions/ping" not in page


def test_placement_is_not_authorization():
    client, ma = make_client(actions=[Action("sync", _noop, where="detail")])
    user = ma.create({"email": "a@example.com"})
    response = client.post(
        "/admin/users/actions/sync", data={"pks": [str(user.id)]}, headers=csrf(client), follow_redirects=False
    )
    assert response.status_code == 303
