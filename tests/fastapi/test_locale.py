from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import Principal
from polyadmin.fastapi.router import create_router
from polyadmin.i18n import get_locale
from tests.core.test_i18n import write_catalog
from tests.core.test_model_admin import InMemoryUserAdmin

HELLO = '{% extends "admin/base.html" %}{% block content %}<p id="greeting">{{ _("Hello") }}</p><p id="lang">{{ locale }}</p>{% endblock %}'


def hello_client(tmp_path, **admin_kwargs):
    catalogs = write_catalog(tmp_path / "locale", "fr", {"Hello": "Bonjour", "Broadcast Message": "Message diffusé"}, domain="host")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "hello.html").write_text(HELLO)
    seen = {}

    async def hello(ctx):
        seen["locale"] = get_locale()
        return ctx.render("pages/hello.html")

    admin = Admin(catalogs=[(catalogs, "host")], **admin_kwargs)
    admin.route("/hello", hello, label="Broadcast Message")
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin", template_dirs=(tmp_path,)), prefix="/admin")
    return TestClient(app), seen


def test_page_renders_in_the_accept_language_locale(tmp_path):
    client, _ = hello_client(tmp_path)
    page = client.get("/admin/hello", headers={"Accept-Language": "fr-CA,fr;q=0.9"}).text
    assert '<p id="greeting">Bonjour</p>' in page
    assert '<html lang="fr"' in page
    english = client.get("/admin/hello").text
    assert '<p id="greeting">Hello</p>' in english
    assert '<html lang="en"' in english


def test_locale_cookie_beats_accept_language(tmp_path):
    client, _ = hello_client(tmp_path)
    client.cookies.set("admin_locale", "en")
    page = client.get("/admin/hello", headers={"Accept-Language": "fr"}).text
    assert '<p id="greeting">Hello</p>' in page


class CountingAuthenticator:
    def __init__(self):
        self.calls = 0

    def authenticate(self, request):
        self.calls += 1
        return Principal(id="u", extra={"locale": "fr"})


def test_resolver_sees_the_principal_and_authentication_runs_once(tmp_path):
    auth = CountingAuthenticator()
    client, _ = hello_client(
        tmp_path,
        authenticator=auth,
        locale_resolver=lambda request, principal: principal.extra.get("locale") if principal else None,
    )
    page = client.get("/admin/hello", headers={"Accept-Language": "en"}).text
    assert "Bonjour" in page
    assert auth.calls == 1


def test_handlers_see_the_locale_through_the_context_variable(tmp_path):
    client, seen = hello_client(tmp_path)
    client.get("/admin/hello", headers={"Accept-Language": "fr"})
    assert seen["locale"] == "fr"


def test_tojson_translation_is_safe_in_a_single_quoted_attribute(tmp_path):
    catalogs = write_catalog(tmp_path / "locale", "fr", {"Dark mode": "Mode d'affichage \"sombre\""}, domain="host")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "x.html").write_text(
        """{% extends "admin/base.html" %}{% block content %}<span id="x" x-text='dark ? {{ _("Dark mode")|tojson }} : ""'></span>{% endblock %}"""
    )

    async def page(ctx):
        return ctx.render("pages/x.html")

    admin = Admin(catalogs=[(catalogs, "host")])
    admin.route("/x", page)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin", template_dirs=(tmp_path,)), prefix="/admin")
    text = TestClient(app).get("/admin/x", headers={"Accept-Language": "fr"}).text
    assert """x-text='dark ? "Mode d\\u0027affichage \\"sombre\\"" : ""'""" in text


def test_error_pages_use_the_request_locale():
    admin = Admin(model_admins=[InMemoryUserAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin/users/999", headers={"Accept-Language": "ru"}).text
    assert '<html lang="ru"' in page
