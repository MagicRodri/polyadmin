import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_i18n import write_catalog
from tests.core.test_model_admin import InMemoryUserAdmin
from tests.fastapi.test_login import FakeLoginBackend


@pytest.fixture
def switcher_client(tmp_path):
    """fr and ru need catalogs to be supported; the framework doesn't ship
    any yet, so these tests bring their own (empty) ones."""
    write_catalog(tmp_path, "fr", {}, domain="host")
    write_catalog(tmp_path, "ru", {}, domain="host")

    def build(**admin_kwargs):
        user_admin = InMemoryUserAdmin()
        user_admin.create({"email": "a@example.com"})
        admin = Admin(model_admins=[user_admin], catalogs=[(tmp_path, "host")], **admin_kwargs)
        app = FastAPI()
        app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
        return TestClient(app)

    return build


def test_locale_switch_sets_the_cookie_and_redirects_back(switcher_client):
    client = switcher_client()
    response = client.post(
        "/admin/locale",
        data={"locale": "fr-CA"},
        headers={**csrf(client), "Referer": "http://testserver/admin/users?page=2"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users?page=2"
    cookie = response.headers["set-cookie"].lower()
    for want in ("admin_locale=fr", "path=/admin", "max-age=31536000", "httponly", "samesite=lax"):
        assert want in cookie


def test_locale_switch_ignores_an_unsupported_locale(switcher_client):
    client = switcher_client()
    response = client.post("/admin/locale", data={"locale": "de"}, headers=csrf(client), follow_redirects=False)
    assert response.status_code == 303
    assert "admin_locale" not in response.headers.get("set-cookie", "")


def test_locale_switch_refuses_an_offsite_referer(switcher_client):
    client = switcher_client()
    response = client.post(
        "/admin/locale", data={"locale": "fr"}, headers={**csrf(client), "Referer": "https://evil.example/phish"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/admin"


def test_locale_switch_requires_csrf(switcher_client):
    client = switcher_client()
    assert client.post("/admin/locale", data={"locale": "fr"}, follow_redirects=False).status_code == 403


def test_switcher_renders_in_the_header(switcher_client):
    page = switcher_client().get("/admin/users").text
    for want in ('action="/admin/locale"', 'value="fr"', "Français", "Русский", 'aria-checked="true"'):
        assert want in page


def test_no_switcher_with_one_locale(switcher_client):
    client = switcher_client(locales=["en"])
    assert 'action="/admin/locale"' not in client.get("/admin/users").text
    assert client.post("/admin/locale", data={"locale": "en"}, headers=csrf(client)).status_code in (404, 405)


def test_no_switcher_when_disabled(switcher_client):
    client = switcher_client(locale_switcher=False)
    assert 'action="/admin/locale"' not in client.get("/admin/users").text
    response = client.post("/admin/locale", data={"locale": "fr"}, headers=csrf(client), follow_redirects=False)
    assert response.status_code in (404, 405)
    assert "admin_locale" not in response.headers.get("set-cookie", "")


def test_locale_cookie_is_secure_over_https(switcher_client):
    https = TestClient(switcher_client().app, base_url="https://testserver")
    response = https.post("/admin/locale", data={"locale": "fr"}, headers=csrf(https), follow_redirects=False)
    assert "secure" in response.headers["set-cookie"].lower()
    plain = switcher_client()
    response = plain.post("/admin/locale", data={"locale": "fr"}, headers=csrf(plain), follow_redirects=False)
    assert "secure" not in response.headers["set-cookie"].lower()


def test_switcher_renders_on_the_login_page(tmp_path):
    write_catalog(tmp_path, "fr", {}, domain="host")
    backend = FakeLoginBackend()
    admin = Admin(catalogs=[(tmp_path, "host")], authenticator=backend, login_backend=backend)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    page = client.get("/admin/login").text
    assert 'action="/admin/locale"' in page

