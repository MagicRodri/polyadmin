"""Strings built in Python code -- validation, flash/success messages,
error pages, login messages, export headers -- translate from the
host's catalog. Mirrors Go's fiber/codestrings_test.go.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.fastapi.router import create_router
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
