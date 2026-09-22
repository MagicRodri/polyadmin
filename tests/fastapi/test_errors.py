from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator, DenyAllAuthenticator, Principal
from polyadmin.core.authorization import DenyAllAuthorizer
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


def _client(admin):
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app, follow_redirects=False)


def test_not_found_renders_a_page_not_bare_text():
    client = _client(Admin(model_admins=[InMemoryUserAdmin()]))
    response = client.get("/admin/users/999999")
    assert response.status_code == 404
    page = response.text
    for want in ("<!doctype html>", "polyadmin-theme", "404", "Back to the admin"):
        assert want in page, want
    assert page.strip() != "Not found"


def test_forbidden_renders_a_page():
    client = _client(
        Admin(
            model_admins=[InMemoryUserAdmin()],
            authenticator=AllowAllAuthenticator(Principal(id="u", display_name="U")),
            authorizer=DenyAllAuthorizer(),
        )
    )
    response = client.get("/admin/users")
    assert response.status_code == 403
    assert "<!doctype html>" in response.text
    assert "403" in response.text
    # Signed in, so there is somewhere to go back to.
    assert "Back to the admin" in response.text


def test_unauthenticated_page_offers_no_home_link():
    client = _client(
        Admin(model_admins=[InMemoryUserAdmin()], authenticator=DenyAllAuthenticator())
    )
    response = client.get("/admin/users")
    assert response.status_code == 401
    assert "Sign-in required" in response.text
    assert "Back to the admin" not in response.text


def test_htmx_failure_returns_a_fragment_not_a_page():
    client = _client(
        Admin(
            model_admins=[InMemoryUserAdmin()],
            authenticator=AllowAllAuthenticator(Principal(id="u")),
            authorizer=DenyAllAuthorizer(),
        )
    )
    page = client.get("/admin/users", headers={"HX-Request": "true"}).text
    assert "<!doctype html>" not in page
    assert 'role="alert"' in page


def test_csrf_rejection_renders_a_page():
    client = _client(Admin(model_admins=[InMemoryUserAdmin()]))
    # Deliberately no csrf() helper here: this asserts the rejection.
    response = client.post("/admin/users/create", data={})
    assert response.status_code == 403
    assert "Security check failed" in response.text
    assert "Reload and try again" in response.text
