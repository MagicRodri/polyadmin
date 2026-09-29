from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.audit import AUDIT_UPDATE
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


class BulkUserAdmin(InMemoryUserAdmin):
    bulk_edit_fields = ("email", "is_active")


class RecordingLogger:
    def __init__(self):
        self.entries = []

    def record(self, entry):
        self.entries.append(entry)


def make_client(model_admin=None, **admin_kwargs):
    users = model_admin or BulkUserAdmin()
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users], **admin_kwargs), base_path="/admin"), prefix="/admin")
    return TestClient(app), users


def post(client, data):
    return client.post("/admin/users/actions/bulk_edit", data=data, follow_redirects=False, headers=csrf(client))


def test_bulk_edit_form_has_a_change_box_per_field():
    client, users = make_client()
    a = users.create({"email": "a@x.com", "is_active": True})
    response = post(client, {"pks": [str(a.id)]})
    assert response.status_code == 200
    assert 'name="_change_email"' in response.text
    assert 'name="_change_is_active"' in response.text


def test_only_ticked_fields_are_applied():
    client, users = make_client()
    a = users.create({"email": "a@x.com", "is_active": True})
    b = users.create({"email": "b@x.com", "is_active": True})
    response = post(
        client,
        {"pks": [str(a.id), str(b.id)], "_confirmed": "1", "_change_is_active": "1", "email": "hijack@x.com"},
    )
    assert response.status_code == 303
    assert (a.is_active, b.is_active) == (False, False)
    assert (a.email, b.email) == ("a@x.com", "b@x.com")


def test_update_receives_only_ticked_keys():
    seen = []

    class Spy(BulkUserAdmin):
        def update(self, obj, data):
            seen.append(set(data))
            return super().update(obj, data)

    client, users = make_client(Spy())
    a = users.create({"email": "a@x.com", "is_active": True})
    post(client, {"pks": [str(a.id)], "_confirmed": "1", "_change_email": "1", "email": "new@x.com"})
    assert seen == [{"email"}]


def test_nothing_ticked_redisplays_with_a_message():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, {"pks": [str(a.id)], "_confirmed": "1"})
    assert response.status_code == 422
    assert "Choose at least one field to change." in response.text


def test_ticked_field_is_validated():
    client, users = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, {"pks": [str(a.id)], "_confirmed": "1", "_change_email": "1", "email": ""})
    assert response.status_code == 422
    assert a.email == "a@x.com"


def test_object_readonly_for_one_record_blocks_the_whole_edit():
    class PerObject(BulkUserAdmin):
        def get_readonly_fields(self, obj=None):
            return ["email"] if obj is not None and obj.id == 2 else []

    client, users = make_client(PerObject())
    a = users.create({"email": "a@x.com"})
    b = users.create({"email": "b@x.com"})
    response = post(
        client, {"pks": [str(a.id), str(b.id)], "_confirmed": "1", "_change_email": "1", "email": "z@x.com"}
    )
    assert response.status_code == 422
    assert 'id="action-form-blocked"' in response.text
    assert (a.email, b.email) == ("a@x.com", "b@x.com")


def test_object_permission_denied_blocks_the_whole_edit():
    class DenyUpdateOnTwo:
        def can(self, principal, permission, resource=None):
            return not (permission.endswith(".update") and getattr(resource, "id", None) == 2)

    client, users = make_client(authorizer=DenyUpdateOnTwo())
    a = users.create({"email": "a@x.com", "is_active": True})
    b = users.create({"email": "b@x.com", "is_active": True})
    response = post(client, {"pks": [str(a.id), str(b.id)], "_confirmed": "1", "_change_is_active": "1"})
    assert response.status_code == 422
    assert (a.is_active, b.is_active) == (True, True)


def test_each_record_gets_an_update_audit_entry():
    logger = RecordingLogger()
    client, users = make_client(audit_logger=logger)
    a = users.create({"email": "a@x.com", "is_active": True})
    b = users.create({"email": "b@x.com", "is_active": True})
    post(client, {"pks": [str(a.id), str(b.id)], "_confirmed": "1", "_change_is_active": "1"})
    assert [(e.action, e.object_pk) for e in logger.entries] == [(AUDIT_UPDATE, a.id), (AUDIT_UPDATE, b.id)]


def test_bulk_edit_is_in_the_list_bulk_bar():
    client, users = make_client()
    users.create({"email": "a@x.com"})
    response = client.get("/admin/users")
    assert "/admin/users/actions/bulk_edit" in response.text


def test_the_model_admins_own_validate_runs_on_ticked_fields():
    class Strict(BulkUserAdmin):
        def validate(self, data):
            errors = super().validate(data)
            if data.get("is_active") is False:
                errors.setdefault("is_active", []).append("Users cannot be deactivated in bulk.")
            return errors

    client, users = make_client(Strict())
    a = users.create({"email": "a@x.com", "is_active": True})
    response = post(client, {"pks": [str(a.id)], "_confirmed": "1", "_change_is_active": "1"})
    assert response.status_code == 422
    assert "Users cannot be deactivated in bulk." in response.text
    assert a.is_active is True
