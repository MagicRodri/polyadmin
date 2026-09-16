"""delete_selected's confirmation page when the ModelAdmin previews deletes."""

from polyadmin.core.action import DELETE_SELECTED_NAME, Action
from polyadmin.core.delete import DeletePreview, selection_fingerprint
from tests.conftest import csrf
from tests.fastapi.test_delete_preview import make, protected_invoices


def no_cascade(objects):
    return DeletePreview()


def two_users(preview_fn=no_cascade):
    client, users, _ = make(preview_fn)
    users.create({"email": "b@example.com"})
    return client, users


def post(client, data, headers=None):
    return client.post("/admin/users/actions/delete_selected", data=data, headers={**csrf(client), **(headers or {})})


def test_delete_selected_asks_first_when_previewing():
    client, users = two_users()
    response = post(client, {"pks": ["1", "2"]})
    for want in ["Delete 2 records?", 'name="_confirmed"', 'name="pks" value="1"', 'name="pks" value="2"', "a@example.com", 'id="delete-confirm"']:
        assert want in response.text, want
    assert response.status_code == 200 and len(users.get_queryset()) == 2


def test_confirmed_delete_selected_deletes():
    client, users = two_users()
    response = post(client, {"pks": ["1", "2"], "_confirmed": "1"})
    assert response.status_code == 303 and users.get_queryset() == []


def test_confirmed_delete_selected_is_refused_when_blocked():
    client, users = two_users(protected_invoices)
    response = post(client, {"pks": ["1"], "_confirmed": "1"})
    assert "This can&#39;t be deleted" in response.text and 'id="delete-confirm"' not in response.text
    assert len(users.get_queryset()) == 2


def test_select_all_carries_filters_and_a_fingerprint():
    client, users = two_users()
    page = post(client, {"_select_all": "1", "search": "a@"}).text
    fp = selection_fingerprint(users, [users.get_object(1)])
    for want in ['name="_select_all" value="1"', 'name="search" value="a@"', f'name="_fingerprint" value="{fp}"', "Delete 1 record?"]:
        assert want in page, want
    assert 'name="pks"' not in page


def test_changed_selection_is_shown_again_and_nothing_is_deleted():
    client, users = two_users()
    response = post(client, {"_select_all": "1", "_confirmed": "1", "_fingerprint": "stale"})
    assert "The selection changed since you reviewed it." in response.text
    assert len(users.get_queryset()) == 2


def test_confirmed_select_all_with_the_reviewed_fingerprint_deletes():
    client, users = two_users()
    fp = selection_fingerprint(users, users.get_queryset())
    response = post(client, {"_select_all": "1", "_confirmed": "1", "_fingerprint": fp})
    assert response.status_code == 303 and users.get_queryset() == []


def test_confirmation_returns_to_the_list_it_came_from():
    client, _ = two_users()
    page = post(client, {"pks": ["1"]}, {"referer": "http://testserver/admin/users?search=a"}).text
    assert 'name="_return" value="/admin/users?search=a"' in page
    response = post(client, {"pks": ["1"], "_confirmed": "1", "_return": "/admin/users?search=a"},
                    {"referer": "http://testserver/admin/users/actions/delete_selected"})
    assert response.headers["location"] == "/admin/users?search=a"


def test_overridden_delete_selected_still_previews():
    client, users, _ = make(no_cascade)
    users.actions = [Action(DELETE_SELECTED_NAME, lambda model_admin, objects, principal: "")]
    assert 'name="_confirmed"' in post(client, {"pks": ["1"]}).text


def test_bulk_bar_marks_the_preview_and_keeps_other_modals():
    client, users, _ = make(no_cascade)
    users.actions = [Action("archive", lambda model_admin, objects, principal: "", confirm="Archive them?")]
    page = client.get("/admin/users").text
    assert "data-preview" in page and 'data-confirm="Archive them?"' in page
    assert 'data-confirm="Delete the selected records? This cannot be undone."' not in page
