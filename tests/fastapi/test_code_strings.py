"""Strings built in Python code -- validation, flash/success messages,
error pages, login messages, export headers -- translate from the
host's catalog. Mirrors Go's fiber/codestrings_test.go.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.fastapi.router import create_router
from polyadmin.i18n import pseudo
from tests.conftest import csrf
from tests.core.test_i18n import write_catalog
from tests.core.test_model_admin import InMemoryUserAdmin

FR = {"Accept-Language": "fr"}
ENTRIES = {
    "User": "Utilisateur",
    "Email": "Courriel",
    "%(name)s created.": "%(name)s : enregistrement créé.",
    "%(label)s is required.": "%(label)s est obligatoire.",
    "Not found": "Introuvable",
    "No items selected.": "Aucun élément sélectionné.",
    ("Deleted %(num)d record.", "Deleted %(num)d records."): [
        "%(num)d enregistrement supprimé.",
        "%(num)d enregistrements supprimés.",
    ],
}


def french_client(tmp_path):
    catalogs = write_catalog(tmp_path, "fr", ENTRIES, domain="host", plural_forms="nplurals=2; plural=(n > 1);")
    users = InMemoryUserAdmin()
    admin = Admin(model_admins=[users], catalogs=[(catalogs, "host")])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), users


def test_flash_is_translated(tmp_path):
    client, _ = french_client(tmp_path)
    page = client.post("/admin/users/create", data={"email": "a@example.com"}, headers={**csrf(client), **FR}).text
    assert "Utilisateur : enregistrement créé." in page


def test_required_error_is_translated(tmp_path):
    client, _ = french_client(tmp_path)
    page = client.post("/admin/users/create", data={"email": ""}, headers={**csrf(client), **FR}).text
    assert "Courriel est obligatoire." in page


def test_error_page_is_translated(tmp_path):
    client, _ = french_client(tmp_path)
    assert "Introuvable" in client.get("/admin/users/999", headers=FR).text


def test_built_in_action_messages_are_translated(tmp_path):
    client, users = french_client(tmp_path)
    users.create({"email": "a@example.com"})
    page = client.post("/admin/users/actions/delete_selected", data={"pks": "1"}, headers={**csrf(client), **FR}).text
    assert "1 enregistrement supprimé." in page
    page = client.post("/admin/users/actions/delete_selected", data={}, headers={**csrf(client), **FR}).text
    assert "Aucun élément sélectionné." in page


def test_export_headers_are_translated(tmp_path):
    client, users = french_client(tmp_path)
    users.create({"email": "a@example.com"})
    first_line = client.get("/admin/users/export/csv", headers=FR).text.splitlines()[0]
    assert "Courriel" in first_line


def test_delete_selected_flash_is_not_double_bracketed_under_pseudo_locale(tmp_path):
    # R5: build_action_handler re-translates a built-in action's already
    # -translated result (delete_selected_action returns an ngettext
    # call's output) before flashing it. Under the pseudo locale that
    # re-translation must not double-bracket it into "[[...]]".
    users = InMemoryUserAdmin()
    users.create({"email": "a@example.com"})
    admin = Admin(model_admins=[users], pseudo_locale=True)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    client.cookies.set("admin_locale", "en-XA")
    page = client.post("/admin/users/actions/delete_selected", data={"pks": "1"}, headers=csrf(client)).text
    single = pseudo("Deleted %(num)d record.") % {"num": 1}
    assert single in page
    assert pseudo(single) not in page


def test_russian_flash_round_trips_in_an_ascii_cookie():
    """A cookie value must be ASCII; a translated flash message is not.
    json.dumps escapes it to \\uXXXX and Starlette quotes the rest, so the
    Set-Cookie header stays ASCII and reading it back restores the text.
    Mirrors Go's TestRussianFlashRoundTripsInAnASCIICookie."""
    users = InMemoryUserAdmin()
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    client.cookies.set("admin_locale", "ru")
    response = client.post(
        "/admin/users/create", data={"email": "a@example.com"}, headers=csrf(client), follow_redirects=False
    )
    assert response.status_code == 303
    flash = [h for h in response.headers.get_list("set-cookie") if h.startswith("admin_messages=")]
    assert flash, "no flash cookie was set"
    assert flash[0].isascii(), flash[0]
    assert "запись создана" in client.get(response.headers["location"]).text


def test_framework_defaults_are_translated():
    """The framework's own fallback strings -- a root page's default label,
    AllowAllAuthenticator's default display name, the empty admin's notice
    -- are framework strings like any other and come out translated.
    Mirrors Go's TestFrameworkDefaultsAreTranslated."""

    async def root_page(ctx):
        return ctx.render_string("")

    admin = Admin(model_admins=[InMemoryUserAdmin()], authenticator=AllowAllAuthenticator())
    admin.route("/", root_page)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    client.cookies.set("admin_locale", "ru")
    page = client.get("/admin/users").text
    assert 'class="truncate">Страница</span>' in page
    assert "Аноним" in page

    app = FastAPI()
    app.include_router(create_router(Admin(), base_path="/admin"), prefix="/admin")
    empty = TestClient(app)
    empty.cookies.set("admin_locale", "ru")
    assert "Нет зарегистрированных ресурсов." in empty.get("/admin").text
