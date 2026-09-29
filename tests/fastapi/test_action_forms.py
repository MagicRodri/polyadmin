from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin import ActionFormError
from polyadmin.core.action import action
from polyadmin.core.admin import Admin
from polyadmin.core.field import ForeignKeyField, StringField
from polyadmin.core.relation import Relation
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin
from tests.fastapi.test_relations import OrganizationAdmin

ORG = Relation("organization", target="organizations", display_field="name")


class FormUserAdmin(InMemoryUserAdmin):
    @action(label="Rename domain", form=[StringField("domain", required=True)], submit_label="Rename")
    def rename_domain(self, objects, principal, data):
        if data["domain"].startswith("."):
            raise ActionFormError({"domain": ["No leading dot."]})
        for obj in objects:
            obj.email = obj.email.split("@")[0] + "@" + data["domain"]
        return f"Renamed {len(objects)}."

    @action(label="Assign org", form=[ForeignKeyField("organization", relation=ORG, required=True)])
    def assign_org(self, objects, principal, data):
        self.assigned = data["organization"]
        return None

    @action(
        label="Assign org with note",
        form=[ForeignKeyField("organization", relation=ORG, required=True), StringField("note", required=True)],
    )
    def assign_org_note(self, objects, principal, data):
        return None


def make_client():
    users, orgs = FormUserAdmin(), OrganizationAdmin()
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users, orgs]), base_path="/admin"), prefix="/admin")
    return TestClient(app), users, orgs


def post(client, name, data):
    return client.post(f"/admin/users/actions/{name}", data=data, follow_redirects=False, headers=csrf(client))


def test_first_post_renders_the_form_without_running_the_handler():
    client, users, _ = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "rename_domain", {"pks": [str(a.id)]})
    assert response.status_code == 200
    assert 'name="domain"' in response.text
    assert 'name="_confirmed" value="1"' in response.text
    assert f'name="pks" value="{a.id}"' in response.text
    assert ">Rename<" in response.text
    assert a.email == "a@x.com"


def test_confirmed_post_runs_the_handler_with_parsed_data():
    client, users, _ = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "rename_domain", {"pks": [str(a.id)], "_confirmed": "1", "domain": "y.org"})
    assert response.status_code == 303
    assert a.email == "a@y.org"


def test_field_validation_errors_redisplay_the_form_with_values():
    client, users, _ = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "rename_domain", {"pks": [str(a.id)], "_confirmed": "1", "domain": ""})
    assert response.status_code == 422
    assert "is required" in response.text
    assert a.email == "a@x.com"


def test_action_form_error_redisplays_with_handler_errors():
    client, users, _ = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "rename_domain", {"pks": [str(a.id)], "_confirmed": "1", "domain": ".bad"})
    assert response.status_code == 422
    assert "No leading dot." in response.text
    assert 'value=".bad"' in response.text


def test_relation_field_uses_the_targets_lookup_when_it_is_searchable():
    client, users, orgs = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(client, "assign_org", {"pks": [str(a.id)]})
    assert "/admin/organizations/lookup" in response.text


def test_relation_value_reaches_the_handler():
    client, users, orgs = make_client()
    acme = orgs.create({"name": "Acme"})
    a = users.create({"email": "a@x.com"})
    response = post(client, "assign_org", {"pks": [str(a.id)], "_confirmed": "1", "organization": str(acme.id)})
    assert response.status_code == 303
    assert str(users.assigned) == str(acme.id)


def test_relation_selection_survives_a_redisplay():
    client, users, orgs = make_client()
    acme = orgs.create({"name": "Acme Widgets"})
    a = users.create({"email": "a@x.com"})
    response = post(
        client, "assign_org_note", {"pks": [str(a.id)], "_confirmed": "1", "organization": str(acme.id), "note": ""}
    )
    assert response.status_code == 422
    assert "Acme Widgets" in response.text
    assert f'value="{acme.id}"' in response.text


def test_select_all_with_changed_selection_does_not_run():
    client, users, _ = make_client()
    a = users.create({"email": "a@x.com"})
    response = post(
        client,
        "rename_domain",
        {"_select_all": "1", "_confirmed": "1", "_fingerprint": "stale", "domain": "y.org"},
    )
    assert response.status_code == 200
    assert "The selection changed" in response.text
    assert a.email == "a@x.com"


def test_select_all_with_matching_fingerprint_runs():
    client, users, _ = make_client()
    a = users.create({"email": "a@x.com"})
    page = post(client, "rename_domain", {"_select_all": "1"})
    fingerprint = page.text.split('name="_fingerprint" value="')[1].split('"')[0]
    response = post(
        client, "rename_domain", {"_select_all": "1", "_confirmed": "1", "_fingerprint": fingerprint, "domain": "y.org"}
    )
    assert response.status_code == 303
    assert a.email == "a@y.org"


def test_form_action_refuses_principals_without_the_action_permission():
    class Guarded(FormUserAdmin):
        @action(form=[StringField("x")], permission="special")
        def guarded(self, objects, principal, data):
            return None

    class DenySpecial:
        def can(self, principal, permission, resource=None):
            return not permission.endswith(".special")

    users = Guarded()
    app = FastAPI()
    app.include_router(
        create_router(Admin(model_admins=[users], authorizer=DenySpecial()), base_path="/admin"), prefix="/admin"
    )
    client = TestClient(app)
    a = users.create({"email": "a@x.com"})
    response = post(client, "guarded", {"pks": [str(a.id)]})
    assert response.status_code == 403


class DenyOrganizations:
    def can(self, principal, permission, resource=None):
        return not permission.startswith("organizations.")


def test_relation_options_are_withheld_when_the_target_is_not_viewable():
    class UnsearchableOrganizationAdmin(OrganizationAdmin):
        search_fields = []

    users, orgs = FormUserAdmin(), UnsearchableOrganizationAdmin()
    app = FastAPI()
    app.include_router(
        create_router(Admin(model_admins=[users, orgs], authorizer=DenyOrganizations()), base_path="/admin"),
        prefix="/admin",
    )
    client = TestClient(app)
    orgs.create({"name": "Secret Holdings"})
    a = users.create({"email": "a@x.com"})
    response = post(client, "assign_org", {"pks": [str(a.id)]})
    assert response.status_code == 200
    assert "Secret Holdings" not in response.text


def test_relation_label_is_withheld_when_the_target_is_not_viewable():
    users, orgs = FormUserAdmin(), OrganizationAdmin()
    app = FastAPI()
    app.include_router(
        create_router(Admin(model_admins=[users, orgs], authorizer=DenyOrganizations()), base_path="/admin"),
        prefix="/admin",
    )
    client = TestClient(app)
    secret = orgs.create({"name": "Secret Holdings"})
    a = users.create({"email": "a@x.com"})
    response = post(
        client, "assign_org_note", {"pks": [str(a.id)], "_confirmed": "1", "organization": str(secret.id), "note": ""}
    )
    assert response.status_code == 422
    assert "Secret Holdings" not in response.text
