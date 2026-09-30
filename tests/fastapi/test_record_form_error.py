from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.core.model_admin import RecordFormError
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


class RejectingUserAdmin(InMemoryUserAdmin):
    def create(self, data):
        raise RecordFormError({"email": ["Адрес уже занят."]})

    def update(self, obj, data):
        raise RecordFormError({"": ["Запись заблокирована."]})


def _client():
    user_admin = RejectingUserAdmin()
    admin = Admin(model_admins=[user_admin], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_create_rejected_by_record_form_error_redisplays_the_form():
    client, _ = _client()
    response = client.post("/admin/users/create", data={"email": "x@example.com"}, headers=csrf(client))
    assert response.status_code == 422
    assert "Адрес уже занят." in response.text
    assert "x@example.com" in response.text


def test_update_rejected_by_record_form_error_redisplays_the_form():
    client, user_admin = _client()
    user = InMemoryUserAdmin.create(user_admin, {"email": "old@example.com"})
    response = client.post(f"/admin/users/{user.id}/edit", data={"email": "new@example.com"}, headers=csrf(client))
    assert response.status_code == 422
    assert "Запись заблокирована." in response.text
