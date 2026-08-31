from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator, DenyAllAuthenticator, Principal
from polyadmin.core.authorization import AllowAllAuthorizer, DenyAllAuthorizer, SuperuserAuthorizer
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin
from tests.conftest import csrf


def make_client(*, authenticator=None, authorizer=None):
    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin], authenticator=authenticator, authorizer=authorizer)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_no_authenticator_configured_allows_everything():
    client, _ = make_client()
    assert client.get("/admin/users").status_code == 200


def test_unauthenticated_request_is_rejected():
    client, _ = make_client(authenticator=DenyAllAuthenticator())
    response = client.get("/admin/users")
    assert response.status_code == 401


def test_authenticated_but_unauthorized_request_is_rejected():
    client, _ = make_client(
        authenticator=AllowAllAuthenticator(Principal(id="u1", is_superuser=False)),
        authorizer=SuperuserAuthorizer(),
    )
    response = client.get("/admin/users")
    assert response.status_code == 403


def test_authenticated_and_authorized_request_succeeds():
    client, _ = make_client(
        authenticator=AllowAllAuthenticator(Principal(id="u1", is_superuser=True)),
        authorizer=SuperuserAuthorizer(),
    )
    response = client.get("/admin/users")
    assert response.status_code == 200


def test_all_crud_routes_are_gated():
    client, user_admin = make_client(authenticator=DenyAllAuthenticator())
    user = user_admin.create({"email": "john@example.com"})

    assert client.get("/admin").status_code == 401
    assert client.get("/admin/users").status_code == 401
    assert client.get(f"/admin/users/{user.id}").status_code == 401
    assert client.get("/admin/users/create").status_code == 401
    assert client.post("/admin/users/create", data={}, headers=csrf(client)).status_code == 401
    assert client.get(f"/admin/users/{user.id}/edit").status_code == 401
    assert (
        client.post(f"/admin/users/{user.id}/edit", data={}, headers=csrf(client)).status_code
        == 401
    )
    assert client.get(f"/admin/users/{user.id}/delete").status_code == 401
    assert client.post(f"/admin/users/{user.id}/delete", headers=csrf(client)).status_code == 401
    assert (
        client.request(
            "DELETE", f"/admin/users/{user.id}/delete", headers=csrf(client)
        ).status_code
        == 401
    )


def test_deny_all_authorizer_still_requires_authentication_first():
    # No authenticator configured (so "principal" is always None) but
    # DenyAllAuthorizer denies regardless -- confirms authz is checked
    # even without an authenticator.
    client, _ = make_client(authorizer=DenyAllAuthorizer())
    assert client.get("/admin/users").status_code == 403


def test_edit_and_delete_controls_hidden_without_permission():
    class ViewOnlyAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission.endswith(".list") or permission.endswith(".view")

    client, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=ViewOnlyAuthorizer()
    )
    user_admin.create({"email": "john@example.com"})

    response = client.get("/admin/users")
    assert response.status_code == 200
    # Row actions render as one dropdown-menu's items rather than
    # standalone icon buttons -- see components/ui/table.html.
    assert ">Edit</span>" not in response.text
    assert ">Delete</span>" not in response.text
    assert ">View</span>" in response.text
    assert "New User" not in response.text


def test_edit_route_still_enforced_even_if_hidden():
    class ViewOnlyAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission.endswith(".list") or permission.endswith(".view")

    client, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=ViewOnlyAuthorizer()
    )
    user = user_admin.create({"email": "john@example.com"})

    assert client.get(f"/admin/users/{user.id}/edit").status_code == 403
    assert (
        client.post(
            f"/admin/users/{user.id}/edit",
            data={"email": "x@example.com"},
            headers=csrf(client),
        ).status_code
        == 403
    )
    assert user.email == "john@example.com"
