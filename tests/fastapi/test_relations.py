from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.field import ForeignKeyField, StringField
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.relation import Relation
from polyadmin.fastapi.router import create_router


class Organization:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class User:
    def __init__(self, id, email, organization=None):
        self.id = id
        self.email = email
        self.organization = organization


class OrganizationAdmin(ModelAdmin):
    model = Organization
    slug = "organizations"
    list_display = ["id", "name"]
    form_fields = ["name"]
    search_fields = ["name"]
    fields = [StringField("name", required=True)]

    def __init__(self):
        super().__init__()
        self._store: dict[int, Organization] = {}
        self._next_id = 1

    def get_queryset(self):
        return list(self._store.values())

    def get_object(self, pk):
        try:
            return self._store.get(int(pk))
        except (TypeError, ValueError):
            return None

    def create(self, data):
        obj = Organization(id=self._next_id, name=data["name"])
        self._store[obj.id] = obj
        self._next_id += 1
        return obj


ORG_RELATION = Relation("organization", target="organizations", display_field="name")


class UserAdmin(ModelAdmin):
    model = User
    slug = "users"
    list_display = ["id", "email", "organization"]
    detail_fields = ["id", "email", "organization"]
    form_fields = ["email", "organization"]
    fields = [
        StringField("email", required=True),
        ForeignKeyField("organization", relation=ORG_RELATION),
    ]

    def __init__(self):
        super().__init__()
        self._store: dict[int, User] = {}
        self._next_id = 1

    def get_queryset(self):
        return list(self._store.values())

    def get_object(self, pk):
        try:
            return self._store.get(int(pk))
        except (TypeError, ValueError):
            return None

    def create(self, data):
        obj = User(id=self._next_id, email=data["email"])
        self._store[obj.id] = obj
        self._next_id += 1
        return obj


def make_client():
    org_admin = OrganizationAdmin()
    user_admin = UserAdmin()
    admin = Admin(model_admins=[user_admin, org_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), admin, user_admin, org_admin


def test_list_renders_related_link():
    client, _, user_admin, org_admin = make_client()
    acme = org_admin.create({"name": "Acme"})
    user_admin._store[1] = User(1, "john@example.com", organization=acme)
    user_admin._next_id = 2

    response = client.get("/admin/users")
    assert response.status_code == 200
    assert 'href="/admin/organizations/1"' in response.text
    assert ">Acme<" in response.text


def test_list_shows_dash_when_relation_is_none():
    client, _, user_admin, _ = make_client()
    user_admin._store[1] = User(1, "john@example.com", organization=None)
    user_admin._next_id = 2

    response = client.get("/admin/users")
    assert "&mdash;" in response.text


def test_detail_renders_related_link():
    client, _, user_admin, org_admin = make_client()
    acme = org_admin.create({"name": "Acme"})
    user_admin._store[1] = User(1, "john@example.com", organization=acme)
    user_admin._next_id = 2

    response = client.get("/admin/users/1")
    assert response.status_code == 200
    assert 'href="/admin/organizations/1"' in response.text
    assert ">Acme<" in response.text


def test_related_link_hidden_when_target_not_viewable():
    org_admin = OrganizationAdmin()
    org_admin.can_view = False
    user_admin = UserAdmin()
    admin = Admin(model_admins=[user_admin, org_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    acme = org_admin.create({"name": "Acme"})
    user_admin._store[1] = User(1, "john@example.com", organization=acme)
    user_admin._next_id = 2

    response = client.get("/admin/users/1")
    assert response.status_code == 200
    assert "<a " not in response.text or 'href="/admin/organizations/1"' not in response.text
    assert "Acme" in response.text  # still shown as plain text, just not linked


def test_lookup_route_returns_matching_options():
    client, _, _, org_admin = make_client()
    org_admin.create({"name": "Acme"})
    org_admin.create({"name": "Widgets Inc"})

    response = client.get("/admin/organizations/lookup?q=acme")
    assert response.status_code == 200
    assert 'data-pk="1"' in response.text
    assert "Acme" in response.text
    assert "Widgets Inc" not in response.text


def test_lookup_route_respects_authorization():
    org_admin = OrganizationAdmin()
    user_admin = UserAdmin()

    class DenyAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "organizations.view"

    admin = Admin(model_admins=[user_admin, org_admin], authorizer=DenyAuthorizer())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    response = client.get("/admin/organizations/lookup?q=acme")
    assert response.status_code == 403


def test_create_form_shows_relation_select_with_options():
    client, _, _, org_admin = make_client()
    org_admin.create({"name": "Acme"})

    response = client.get("/admin/users/create")
    assert response.status_code == 200
    assert '<select id="field-organization" name="organization"' in response.text
    assert ">Acme<" in response.text


def test_edit_form_preselects_current_relation():
    client, _, user_admin, org_admin = make_client()
    acme = org_admin.create({"name": "Acme"})
    user_admin._store[1] = User(1, "john@example.com", organization=acme)
    user_admin._next_id = 2

    response = client.get("/admin/users/1/edit")
    assert response.status_code == 200
    assert f'<option value="{acme.id}" selected>Acme</option>' in response.text


class AutocompleteUserAdmin(UserAdmin):
    autocomplete_fields = ["organization"]


def _make_autocomplete_client():
    org_admin = OrganizationAdmin()
    user_admin = AutocompleteUserAdmin()
    admin = Admin(model_admins=[user_admin, org_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin, org_admin


def test_autocomplete_field_renders_combobox_not_select():
    client, _, org_admin = _make_autocomplete_client()
    org_admin.create({"name": "Acme"})

    response = client.get("/admin/users/create")
    assert response.status_code == 200
    assert "selectItem(" in response.text
    assert 'id="combobox-results-organization"' in response.text
    assert 'hx-get="/admin/organizations/lookup"' in response.text
    assert '<select id="field-organization"' not in response.text
    # The target's full queryset must not be dumped into the page --
    # that's the whole point of routing this field through /lookup.
    assert "Acme" not in response.text


def test_autocomplete_field_prefills_current_selection_label_on_edit():
    client, user_admin, org_admin = _make_autocomplete_client()
    acme = org_admin.create({"name": "Acme"})
    user_admin._store[1] = User(1, "john@example.com", organization=acme)
    user_admin._next_id = 2

    response = client.get("/admin/users/1/edit")
    assert response.status_code == 200
    assert 'value="Acme"' in response.text
    assert f'value="{acme.id}"' in response.text
