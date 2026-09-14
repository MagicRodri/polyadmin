"""Audit logging."""
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.audit import AuditEntry
from polyadmin.fastapi.router import create_router
from polyadmin.i18n import PSEUDO_LOCALE, pseudo
from tests.conftest import csrf
from tests.fastapi.test_actions import ActionableUserAdmin


class RecordingLogger:
    """The write side only -- deliberately not an AuditReader, so the
    tests can tell the two capabilities apart."""

    def __init__(self, error=None):
        self.entries: list[AuditEntry] = []
        self.error = error

    def record(self, entry):
        self.entries.append(entry)
        if self.error:
            raise self.error


class ReadableLogger(RecordingLogger):
    def history(self, resource, pk, limit):
        return [e for e in self.entries if e.resource == resource]


def audit_client(logger, **admin_kwargs):
    user_admin = ActionableUserAdmin()
    admin = Admin(model_admins=[user_admin], audit_logger=logger, **admin_kwargs)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_create_update_and_delete_are_recorded():
    logger = RecordingLogger()
    client, user_admin = audit_client(logger)

    client.post("/admin/users/create", data={"email": "new@example.com"},
                headers=csrf(client), follow_redirects=False)
    user = user_admin.create({"email": "edit-me@example.com"})
    client.post(f"/admin/users/{user.id}/edit", data={"email": "edited@example.com"},
                headers=csrf(client), follow_redirects=False)
    client.request("DELETE", f"/admin/users/{user.id}/delete", headers=csrf(client))

    assert [e.action for e in logger.entries] == ["create", "update", "delete"]
    for entry in logger.entries:
        assert entry.resource == "users"
        assert isinstance(entry.at, datetime)


def test_delete_entry_keeps_the_records_label():
    # The label is captured at write time because the record may be gone
    # by the time anyone reads the log -- exactly the case for a delete.
    logger = RecordingLogger()
    client, user_admin = audit_client(logger)
    user = user_admin.create({"email": "goodbye@example.com"})

    client.request("DELETE", f"/admin/users/{user.id}/delete", headers=csrf(client))

    assert len(logger.entries) == 1
    assert "goodbye@example.com" in logger.entries[0].object_label


def test_bulk_action_records_one_entry_per_record():
    logger = RecordingLogger()
    client, user_admin = audit_client(logger)
    a = user_admin.create({"email": "a@example.com", "is_active": True})
    b = user_admin.create({"email": "b@example.com", "is_active": True})

    client.post("/admin/users/actions/deactivate",
                data={"pks": [str(a.id), str(b.id)]},
                headers=csrf(client), follow_redirects=False)

    assert len(logger.entries) == 2
    assert {e.action for e in logger.entries} == {"deactivate"}


def test_nothing_is_recorded_when_the_change_is_rejected():
    logger = RecordingLogger()
    client, _ = audit_client(logger)

    response = client.post("/admin/users/create", data={"email": ""},
                           headers=csrf(client), follow_redirects=False)
    assert response.status_code == 422
    assert logger.entries == [], f"a rejected save was recorded: {logger.entries}"


def test_a_logger_error_does_not_fail_the_change():
    # The change already happened; showing an error next to it is a lie.
    logger = RecordingLogger(error=RuntimeError("log is down"))
    client, _ = audit_client(logger)

    response = client.post("/admin/users/create", data={"email": "a@example.com"},
                           headers=csrf(client), follow_redirects=False)
    assert response.status_code < 400


def test_no_logger_configured_records_nothing_and_still_works():
    client, _ = audit_client(None)
    response = client.post("/admin/users/create", data={"email": "a@example.com"},
                           headers=csrf(client), follow_redirects=False)
    assert response.status_code < 400


def test_history_panel_appears_only_for_a_readable_logger():
    write_only = RecordingLogger()
    client, user_admin = audit_client(write_only)
    user = user_admin.create({"email": "a@example.com"})
    client.post(f"/admin/users/{user.id}/edit", data={"email": "b@example.com"},
                headers=csrf(client), follow_redirects=False)
    assert ">History<" not in client.get(f"/admin/users/{user.id}").text

    readable = ReadableLogger()
    client2, user_admin2 = audit_client(readable)
    user2 = user_admin2.create({"email": "a@example.com"})
    client2.post(f"/admin/users/{user2.id}/edit", data={"email": "b@example.com"},
                 headers=csrf(client2), follow_redirects=False)
    page = client2.get(f"/admin/users/{user2.id}").text
    assert ">History<" in page
    assert "update" in page


def test_history_panel_translates_the_framework_verbs_but_not_action_names():
    # "system" and the framework's own verbs are words on the page; an
    # Action's name is an identifier stored in the log, so it stays as is.
    logger = ReadableLogger()
    client, user_admin = audit_client(logger, pseudo_locale=True)
    user = user_admin.create({"email": "a@example.com"})
    client.post(f"/admin/users/{user.id}/edit", data={"email": "b@example.com"},
                headers=csrf(client), follow_redirects=False)
    logger.entries.append(AuditEntry(at=datetime(2026, 1, 1, tzinfo=UTC), action="mark_active", resource="users", object_pk=user.id))

    client.cookies.set("admin_locale", PSEUDO_LOCALE)
    page = client.get(f"/admin/users/{user.id}").text
    assert f">{pseudo('update')}<" in page
    assert f">{pseudo('system')}<" in page
    assert ">mark_active<" in page
