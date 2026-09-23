"""The built-in bulk delete."""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.action import DELETE_SELECTED_NAME, action
from polyadmin.core.admin import Admin
from polyadmin.core.auth import Principal
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin, User


def _client(model_admin):
    admin = Admin(model_admins=[model_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app, follow_redirects=False)


def test_delete_selected_is_offered_without_declaring_it():
    assert "Delete selected" in _client(InMemoryUserAdmin()).get("/admin/users").text


def test_delete_selected_actually_deletes():
    a = InMemoryUserAdmin()
    a._store = {
        1: User(id=1, email="a@example.com"),
        2: User(id=2, email="b@example.com"),
        3: User(id=3, email="c@example.com"),
    }
    a._next_id = 4
    client = _client(a)
    response = client.post(
        "/admin/users/actions/delete_selected", data={"pks": ["1", "2"]}, headers=csrf(client)
    )
    assert response.status_code in (200, 303)
    remaining = {u.id for u in a.get_queryset()}
    assert 1 not in remaining
    assert 2 not in remaining
    assert 3 in remaining


def test_delete_selected_carries_a_confirmation():
    assert InMemoryUserAdmin().get_action(DELETE_SELECTED_NAME).confirm


def test_delete_selected_requires_the_delete_permission():
    assert InMemoryUserAdmin().get_action(DELETE_SELECTED_NAME).permission == "delete"


def test_delete_selected_is_absent_when_delete_is_disabled():
    class NoDelete(InMemoryUserAdmin):
        can_delete = False

    assert "Delete selected" not in _client(NoDelete()).get("/admin/users").text


def test_delete_selected_can_be_opted_out():
    class OptedOut(InMemoryUserAdmin):
        disable_delete_selected = True

    assert "Delete selected" not in _client(OptedOut()).get("/admin/users").text


def test_overriding_delete_selected_replaces_the_built_in():
    class Custom(InMemoryUserAdmin):
        @action(label="Delete selected")
        def delete_selected(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return "mine ran"

    actions = Custom().get_actions()
    assert [a.name for a in actions] == [DELETE_SELECTED_NAME]
    assert actions[0].label == "Delete selected"
    assert actions[0].handler([], None) == "mine ran"


def test_list_page_translates_the_label_and_confirmation():
    client = _client(InMemoryUserAdmin())
    fr = client.get("/admin/users", headers={"Accept-Language": "fr"}).text
    assert "Supprimer la sélection" in fr
    assert "Supprimer les enregistrements sélectionnés" in fr
    ru = client.get("/admin/users", headers={"Accept-Language": "ru"}).text
    assert "Удалить выбранное" in ru
    assert "Удалить выбранные записи" in ru
