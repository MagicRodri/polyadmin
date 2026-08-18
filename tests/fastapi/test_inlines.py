import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator, Principal
from polyadmin.core.authorization import SuperuserAuthorizer
from polyadmin.core.field import BooleanField, ForeignKeyField, StringField
from polyadmin.core.inline import StackedInline, TabularInline
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.relation import Relation
from polyadmin.fastapi.router import create_router

ORG_RELATION = Relation("organization", target="organizations", display_field="name")


class Organization:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class User:
    def __init__(self, id, email, is_active=True, organization=None):
        self.id = id
        self.email = email
        self.is_active = is_active
        self.organization = organization


def make_organization_admin(*, inline_layout="tabular"):
    inline_cls = TabularInline if inline_layout == "tabular" else StackedInline

    class OrganizationAdmin(ModelAdmin):
        model = Organization
        slug = "organizations"
        list_display = ["id", "name"]
        form_fields = ["name"]
        fields = [StringField("name", required=True)]
        inlines = [inline_cls("users", "organization")]

        def __init__(self, store):
            super().__init__()
            self._store = store

        def get_queryset(self):
            return list(self._store.values())

        def get_object(self, pk):
            try:
                return self._store.get(int(pk))
            except (TypeError, ValueError):
                return None

        def create(self, data):
            obj = Organization(id=max(self._store, default=0) + 1, name=data["name"])
            self._store[obj.id] = obj
            return obj

    return OrganizationAdmin


class UserAdmin(ModelAdmin):
    model = User
    slug = "users"
    list_display = ["id", "email", "is_active", "organization"]
    detail_fields = ["id", "email", "is_active", "organization"]
    form_fields = ["email", "is_active", "organization"]
    fields = [
        StringField("email", required=True),
        BooleanField("is_active", default=True),
        ForeignKeyField("organization", relation=ORG_RELATION),
    ]

    def __init__(self, store, org_store):
        super().__init__()
        self._store = store
        self._org_store = org_store

    def get_queryset(self):
        return list(self._store.values())

    def get_object(self, pk):
        try:
            return self._store.get(int(pk))
        except (TypeError, ValueError):
            return None

    def _resolve_org(self, data):
        pk = data.get("organization")
        if not pk:
            return None
        return self._org_store.get(int(pk))

    def create(self, data):
        obj = User(
            id=max(self._store, default=0) + 1,
            email=data["email"],
            is_active=bool(data.get("is_active")),
            organization=self._resolve_org(data),
        )
        self._store[obj.id] = obj
        return obj

    def update(self, obj, data):
        obj.email = data.get("email", obj.email)
        obj.is_active = bool(data.get("is_active"))
        obj.organization = self._resolve_org(data)
        return obj

    def delete(self, obj):
        del self._store[obj.id]


def make_client(*, inline_layout="tabular", authenticator=None, authorizer=None):
    org_store: dict[int, Organization] = {}
    user_store: dict[int, User] = {}
    org_admin_cls = make_organization_admin(inline_layout=inline_layout)
    org_admin = org_admin_cls(org_store)
    user_admin = UserAdmin(user_store, org_store)
    admin = Admin(model_admins=[org_admin, user_admin], authenticator=authenticator, authorizer=authorizer)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), org_admin, user_admin


def seed_org_with_users(org_admin, user_admin, *emails):
    org = org_admin.create({"name": "Acme"})
    users = [user_admin.create({"email": email, "is_active": True, "organization": str(org.id)}) for email in emails]
    return org, users


def test_inline_section_renders_on_edit_page():
    client, org_admin, user_admin = make_client()
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")
    other_org, other_users = seed_org_with_users(org_admin, user_admin, "outsider@example.com")

    response = client.get(f"/admin/organizations/{org.id}/edit")
    assert response.status_code == 200
    assert 'id="inline-users"' in response.text
    assert "a@example.com" in response.text
    assert "outsider@example.com" not in response.text


def test_inline_section_placeholder_on_create_page():
    client, org_admin, user_admin = make_client()

    response = client.get("/admin/organizations/create")
    assert response.status_code == 200
    assert "Save Organization to add" in response.text
    assert "<table" not in response.text.split('id="inline-users"')[1].split("</div>")[0]


def test_inline_section_readonly_on_detail_page():
    client, org_admin, user_admin = make_client()
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.get(f"/admin/organizations/{org.id}")
    assert response.status_code == 200
    assert 'id="inline-users"' in response.text
    assert "a@example.com" in response.text
    assert "<input" not in response.text.split('id="inline-users"')[1]


def test_inline_create_adds_row_and_returns_section_fragment():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin)

    response = client.post(
        f"/admin/organizations/{org.id}/inlines/users", data={"email": "new@example.com", "is_active": "true"}
    )
    assert response.status_code == 200
    assert "<html" not in response.text.lower()
    assert 'id="inline-users"' in response.text
    assert "new@example.com" in response.text
    assert len(user_admin.get_queryset()) == 1
    assert user_admin.get_queryset()[0].organization is org


def test_inline_create_validation_error_returns_422_with_redisplay():
    client, org_admin, user_admin = make_client()
    org, _ = seed_org_with_users(org_admin, user_admin)

    response = client.post(f"/admin/organizations/{org.id}/inlines/users", data={"email": ""})
    assert response.status_code == 422
    assert len(user_admin.get_queryset()) == 0


def test_inline_update_edits_existing_row():
    client, org_admin, user_admin = make_client()
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.post(
        f"/admin/organizations/{org.id}/inlines/users/{users[0].id}",
        data={"email": "changed@example.com", "is_active": "true"},
    )
    assert response.status_code == 200
    assert user_admin.get_queryset()[0].email == "changed@example.com"


def test_inline_delete_removes_row():
    client, org_admin, user_admin = make_client()
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.request("DELETE", f"/admin/organizations/{org.id}/inlines/users/{users[0].id}")
    assert response.status_code == 200
    assert len(user_admin.get_queryset()) == 0
    assert "a@example.com" not in response.text


def test_inline_create_denied_without_child_create_permission():
    class NoChildCreateAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "users.create"

    client, org_admin, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=NoChildCreateAuthorizer()
    )
    org, _ = seed_org_with_users(org_admin, user_admin)

    response = client.post(f"/admin/organizations/{org.id}/inlines/users", data={"email": "x@example.com"})
    assert response.status_code == 403
    assert len(user_admin.get_queryset()) == 0


def test_inline_update_denied_without_child_update_permission():
    class NoChildUpdateAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "users.update"

    client, org_admin, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=NoChildUpdateAuthorizer()
    )
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.post(
        f"/admin/organizations/{org.id}/inlines/users/{users[0].id}", data={"email": "changed@example.com"}
    )
    assert response.status_code == 403
    assert user_admin.get_queryset()[0].email == "a@example.com"


def test_inline_delete_denied_without_child_delete_permission():
    class NoChildDeleteAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "users.delete"

    client, org_admin, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=NoChildDeleteAuthorizer()
    )
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.request("DELETE", f"/admin/organizations/{org.id}/inlines/users/{users[0].id}")
    assert response.status_code == 403
    assert len(user_admin.get_queryset()) == 1


def test_inline_mutation_denied_without_parent_update_permission():
    class NoParentUpdateAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "organizations.update"

    client, org_admin, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=NoParentUpdateAuthorizer()
    )
    org, _ = seed_org_with_users(org_admin, user_admin)

    response = client.post(f"/admin/organizations/{org.id}/inlines/users", data={"email": "x@example.com"})
    assert response.status_code == 403


def test_inline_section_hidden_without_child_view_permission():
    class NoChildViewAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "users.view"

    client, org_admin, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=NoChildViewAuthorizer()
    )
    org, _ = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.get(f"/admin/organizations/{org.id}/edit")
    assert response.status_code == 200
    assert 'id="inline-users"' not in response.text


def test_stacked_inline_renders_form_per_row():
    client, org_admin, user_admin = make_client(inline_layout="stacked")
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.get(f"/admin/organizations/{org.id}/edit")
    section = response.text.split('id="inline-users"')[1]
    assert "<table" not in section
    assert "<form" in section


def test_tabular_inline_renders_table():
    client, org_admin, user_admin = make_client(inline_layout="tabular")
    org, users = seed_org_with_users(org_admin, user_admin, "a@example.com")

    response = client.get(f"/admin/organizations/{org.id}/edit")
    section = response.text.split('id="inline-users"')[1]
    assert "<table" in section


def test_duplicate_inline_child_slug_raises():
    class DupOrganizationAdmin(ModelAdmin):
        model = Organization
        slug = "organizations"
        form_fields = ["name"]
        fields = [StringField("name", required=True)]
        inlines = [TabularInline("users", "organization"), StackedInline("users", "organization")]

        def get_queryset(self):
            return []

    admin = Admin(model_admins=[DupOrganizationAdmin(), UserAdmin({}, {})])
    with pytest.raises(ValueError):
        create_router(admin, base_path="/admin")


def test_inline_fk_field_must_target_parent_raises():
    class BadFKOrganizationAdmin(ModelAdmin):
        model = Organization
        slug = "organizations"
        form_fields = ["name"]
        fields = [StringField("name", required=True)]
        inlines = [TabularInline("users", "email")]  # "email" isn't a relation field at all

        def get_queryset(self):
            return []

    admin = Admin(model_admins=[BadFKOrganizationAdmin(), UserAdmin({}, {})])
    with pytest.raises(ValueError):
        create_router(admin, base_path="/admin")
