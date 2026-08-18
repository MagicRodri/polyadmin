from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.action import Action
from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


def _deactivate(model_admin, objects, principal):
    for obj in objects:
        obj.is_active = False
    return f"Deactivated {len(objects)} user(s)."


class ActionableUserAdmin(InMemoryUserAdmin):
    actions = [Action("deactivate", _deactivate, confirm="Deactivate selected users?")]


def make_client(model_admin_cls=ActionableUserAdmin, **admin_kwargs):
    user_admin = model_admin_cls()
    admin = Admin(model_admins=[user_admin], **admin_kwargs)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_bulk_action_runs_handler_over_selected_objects():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})
    b = user_admin.create({"email": "b@example.com", "is_active": True})
    user_admin.create({"email": "c@example.com", "is_active": True})

    response = client.post(
        "/admin/users/actions/deactivate",
        data={"pks": [str(a.id), str(b.id)]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert user_admin.get_object(a.id).is_active is False
    assert user_admin.get_object(b.id).is_active is False
    assert user_admin.get_object(3).is_active is True


def test_record_action_from_detail_page_selects_one_object():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})

    response = client.post(
        "/admin/users/actions/deactivate", data={"pks": [str(a.id)]}, follow_redirects=False
    )
    assert response.status_code == 303
    assert user_admin.get_object(a.id).is_active is False


def test_bulk_action_with_no_selection_flashes_warning_and_skips_handler():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})

    response = client.post("/admin/users/actions/deactivate", data={}, follow_redirects=False)
    assert response.status_code == 303
    assert user_admin.get_object(a.id).is_active is True  # handler never ran


def test_unknown_action_name_is_404():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})
    response = client.post("/admin/users/actions/nonexistent", data={"pks": [str(a.id)]})
    assert response.status_code == 404


def test_action_route_not_registered_when_no_actions_declared():
    client, _ = make_client(model_admin_cls=InMemoryUserAdmin)
    response = client.post("/admin/users/actions/deactivate", data={"pks": ["1"]})
    assert response.status_code == 404


def test_action_requires_extra_permission_when_declared():
    class DenyDeactivateAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "users.deactivate"

    client, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=DenyDeactivateAuthorizer()
    )

    class PermissionedUserAdmin(InMemoryUserAdmin):
        actions = [Action("deactivate", _deactivate, permission="deactivate")]

    user_admin = PermissionedUserAdmin()
    admin = Admin(
        model_admins=[user_admin],
        authenticator=AllowAllAuthenticator(),
        authorizer=DenyDeactivateAuthorizer(),
    )
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    a = user_admin.create({"email": "a@example.com"})

    response = client.post("/admin/users/actions/deactivate", data={"pks": [str(a.id)]})
    assert response.status_code == 403
    assert user_admin.get_object(a.id).is_active is True


def test_list_view_shows_action_bar_and_checkboxes():
    client, user_admin = make_client()
    user_admin.create({"email": "a@example.com"})
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert 'id="bulk-actions-form"' in response.text
    assert "Deactivate" in response.text
    assert 'name="pks"' in response.text


def test_list_view_hides_action_bar_when_no_actions_declared():
    client, _ = make_client(model_admin_cls=InMemoryUserAdmin)
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert 'id="bulk-actions-form"' not in response.text


def test_detail_view_shows_record_action_button():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})
    response = client.get(f"/admin/users/{a.id}")
    assert response.status_code == 200
    assert "/admin/users/actions/deactivate" in response.text
    assert "Deactivate" in response.text
