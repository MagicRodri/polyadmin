"""The delete preview on the delete page, and its enforcement (docs/deletes.md).

The msgids carry a straight apostrophe and autoescape turns it into
"&#39;", which the browser shows as "'"; the assertions match the markup.
"""

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.delete import DeleteGroup, DeletePreview
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin
from tests.fastapi import test_inlines as inl


@dataclass
class Note:
    id: int
    email: str
    is_active: bool = True


class NoteAdmin(InMemoryUserAdmin):
    model = Note  # verbose name "Note", slug "notes"


class PreviewUserAdmin(InMemoryUserAdmin):
    def __init__(self, preview_fn):
        super().__init__()
        self.preview_fn = preview_fn

    def delete_preview(self, objects):
        return self.preview_fn(objects)


def make(preview_fn, authorizer=None):
    users, notes = PreviewUserAdmin(preview_fn), NoteAdmin()
    admin = Admin(model_admins=[users, notes], authorizer=authorizer)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    users.create({"email": "a@example.com"})
    notes._store = {1: Note(1, "n1@example.com"), 2: Note(2, "n2@example.com")}
    return TestClient(app, follow_redirects=False), users, notes


def cascade_to_notes(notes_ref, total):
    return lambda objects: DeletePreview(
        cascades=[DeleteGroup(resource="notes", objects=list(notes_ref[0]._store.values()), total=total)]
    )


def protected_invoices(objects):
    return DeletePreview(protected=[DeleteGroup(label="Invoices", objects=["INV-1"])])


class Rule:
    def __init__(self, rule):
        self.rule = rule

    def can(self, principal, permission, resource):
        return self.rule(permission, resource)


def with_cascade(total, authorizer=None):
    ref = [None]
    client, users, notes = make(cascade_to_notes(ref, total), authorizer)
    ref[0] = notes
    return client, users, notes


def test_delete_page_names_the_record():
    client = TestClient(_plain_app())
    page = client.get("/admin/users/1/delete").text
    assert "Delete «john@example.com»?" in page
    assert "This action cannot be undone." in page
    assert 'id="delete-confirm"' in page
    assert "This will also delete" not in page


def _plain_app():
    users = InMemoryUserAdmin()
    users.create({"email": "john@example.com"})
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    return app


def test_delete_page_lists_the_cascade():
    client, _, _ = with_cascade(5)
    page = client.get("/admin/users/1/delete").text
    for want in ["This will also delete", "Note (5)", 'href="/admin/notes/1"', "n2@example.com", "…and 3 more", 'id="delete-confirm"']:
        assert want in page, want


def test_delete_page_counts_records_the_user_cannot_view():
    hide = Rule(lambda p, r: not (p == "notes.view" and getattr(r, "email", "") == "n2@example.com"))
    client, _, _ = with_cascade(2, hide)
    page = client.get("/admin/users/1/delete").text
    assert "1 you can&#39;t view" in page and "n2@example.com" not in page


def test_protected_records_block_the_delete_page():
    client, _, _ = make(protected_invoices)
    page = client.get("/admin/users/1/delete").text
    for want in ["This can&#39;t be deleted", "These records must be removed first:", "Invoices (1)", "INV-1"]:
        assert want in page, want
    assert 'id="delete-confirm"' not in page


def test_cascade_into_a_forbidden_type_blocks():
    client, _, _ = with_cascade(2, Rule(lambda p, r: p != "notes.delete"))
    assert "Your account doesn&#39;t have permission to delete: Note" in client.get("/admin/users/1/delete").text


def test_blocked_delete_post_is_refused():
    client, users, _ = make(protected_invoices)
    response = client.post("/admin/users/1/delete", headers=csrf(client))
    assert response.status_code == 303 and response.headers["location"] == "/admin/users/1/delete"
    assert len(users.get_queryset()) == 1


def test_unblocked_preview_still_deletes():
    client, users, _ = with_cascade(2)
    response = client.post("/admin/users/1/delete", headers=csrf(client))
    assert response.status_code == 303 and users.get_queryset() == []


def test_blocked_htmx_delete_redirects_to_the_delete_page():
    client, users, _ = make(protected_invoices)
    response = client.delete("/admin/users/1/delete", headers={"HX-Request": "true", **csrf(client)})
    assert response.headers.get("HX-Redirect") == "/admin/users/1/delete"
    assert len(users.get_queryset()) == 1


def test_list_row_delete_links_to_the_page_only_when_previewing():
    client, _, _ = make(protected_invoices)
    page = client.get("/admin/users").text
    assert 'href="/admin/users/1/delete"' in page and 'hx-delete="/admin/users/1/delete"' not in page
    plain = TestClient(_plain_app()).get("/admin/users").text
    assert 'hx-delete="/admin/users/1/delete"' in plain


class PreviewingInlineUserAdmin(inl.UserAdmin):
    def delete_preview(self, objects):
        return protected_invoices(objects)


def test_blocked_inline_remove_keeps_the_row_and_says_why():
    org_store, user_store = {}, {}
    org_admin = inl.make_organization_admin()(org_store)
    user_admin = PreviewingInlineUserAdmin(user_store, org_store)
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[org_admin, user_admin]), base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    inl.seed_org_with_users(org_admin, user_admin, "a@example.com")
    response = client.delete("/admin/organizations/1/inlines/users/1", headers={"HX-Request": "true", **csrf(client)})
    assert response.status_code == 200
    assert "This can&#39;t be deleted" in response.text and "INV-1" in response.text
    assert len(user_store) == 1
