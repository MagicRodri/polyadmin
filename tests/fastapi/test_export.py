import io

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


def make_client(**admin_kwargs):
    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin], **admin_kwargs)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_csv_export_downloads_all_rows():
    client, user_admin = make_client()
    user_admin.create({"email": "john@example.com"})
    user_admin.create({"email": "mary@example.com"})

    response = client.get("/admin/users/export/csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="users.csv"' in response.headers["content-disposition"]
    assert "john@example.com" in response.text
    assert "mary@example.com" in response.text


def test_csv_export_respects_search_filter_and_not_pagination():
    client, user_admin = make_client()
    for i in range(30):
        user_admin.create({"email": f"user{i}@example.com"})
    user_admin.create({"email": "john@example.com"})

    response = client.get("/admin/users/export/csv?search=john")
    lines = response.text.strip().splitlines()
    assert len(lines) == 2  # header + exactly the one match, not paginated to 25
    assert "john@example.com" in lines[1]


def test_xlsx_export_downloads():
    import openpyxl

    client, user_admin = make_client()
    user_admin.create({"email": "john@example.com"})

    response = client.get("/admin/users/export/xlsx")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert 'filename="users.xlsx"' in response.headers["content-disposition"]

    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    rows = list(workbook.active.iter_rows(values_only=True))
    assert rows[1][1] == "john@example.com"


def test_export_disabled_when_can_export_false():
    class NoExportUserAdmin(InMemoryUserAdmin):
        can_export = False

    admin = Admin(model_admins=[NoExportUserAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    assert client.get("/admin/users/export/csv").status_code == 404


def test_export_permission_is_independent_of_view():
    class ViewOnlyNoExportAuthorizer:
        def can(self, principal, permission, resource=None):
            return not permission.endswith(".export")

    client, user_admin = make_client(authorizer=ViewOnlyNoExportAuthorizer())
    user_admin.create({"email": "john@example.com"})

    assert client.get("/admin/users").status_code == 200
    assert client.get("/admin/users/export/csv").status_code == 403


def test_export_link_hidden_when_no_export_permission():
    class ViewOnlyNoExportAuthorizer:
        def can(self, principal, permission, resource=None):
            return not permission.endswith(".export")

    client, user_admin = make_client(authorizer=ViewOnlyNoExportAuthorizer())
    user_admin.create({"email": "john@example.com"})

    response = client.get("/admin/users")
    assert "Export CSV" not in response.text
    assert "Export XLSX" not in response.text
