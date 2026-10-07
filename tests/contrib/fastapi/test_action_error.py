from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.action import ActionError, action
from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.contrib.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


class FailingUserAdmin(InMemoryUserAdmin):
    @action(label="Sync")
    def sync(self, objects, principal):
        raise ActionError("Не удалось: #1")

    @action(label="Nothing")
    def nothing(self, objects, principal):
        raise ActionError("Нет фотографий", level="warning")


def _run(action_name):
    user_admin = FailingUserAdmin()
    admin = Admin(model_admins=[user_admin], authenticator=AllowAllAuthenticator())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    user = user_admin.create({"email": "a@example.com"})
    response = client.post(
        f"/admin/users/actions/{action_name}",
        data={"pks": [str(user.id)]},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client.get(response.headers["location"]).text


def test_action_error_redirects_with_an_error_flash():
    page = _run("sync")
    assert 'data-level="error"' in page
    assert "Не удалось: #1" in page


def test_action_error_can_be_a_warning():
    page = _run("nothing")
    assert 'data-level="warning"' in page
    assert "Нет фотографий" in page


class PartlyFailingUserAdmin(InMemoryUserAdmin):
    @action(label="Sync")
    def sync(self, objects, principal):
        raise ActionError("Выполнено для 1 из 2", done=objects[:1])

    def delete(self, obj):
        if obj.email == "stuck@example.com":
            raise RuntimeError("referenced")
        super().delete(obj)


def _audited(action_name):
    from tests.contrib.fastapi.test_audit import RecordingLogger

    logger = RecordingLogger()
    user_admin = PartlyFailingUserAdmin()
    admin = Admin(model_admins=[user_admin], authenticator=AllowAllAuthenticator(), audit_logger=logger)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    first = user_admin.create({"email": "a@example.com"})
    second = user_admin.create({"email": "stuck@example.com"})
    response = client.post(
        f"/admin/users/actions/{action_name}",
        data={"pks": [str(first.id), str(second.id)], "_confirmed": "1"},
        headers=csrf(client),
        follow_redirects=False,
    )
    return response, logger, first


def test_a_partly_failed_action_audits_the_rows_it_did():
    response, logger, first = _audited("sync")
    assert response.status_code == 303
    assert [str(e.object_pk) for e in logger.entries] == [str(first.id)]


def test_a_partly_failed_bulk_delete_audits_the_rows_it_deleted():
    response, logger, first = _audited("delete_selected")
    assert response.status_code == 303
    assert [str(e.object_pk) for e in logger.entries] == [str(first.id)]
