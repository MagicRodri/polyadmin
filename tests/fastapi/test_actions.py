from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.action import Action
from polyadmin.core.filter import BooleanFilter
from polyadmin.core.admin import Admin
from polyadmin.core.auth import AllowAllAuthenticator
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin
from tests.conftest import csrf


def _deactivate(model_admin, objects, principal):
    for obj in objects:
        obj.is_active = False
    return f"Deactivated {len(objects)} user(s)."


class ActionableUserAdmin(InMemoryUserAdmin):
    actions = [Action("deactivate", _deactivate, confirm="Deactivate selected users?")]


def make_client(model_admin_cls=ActionableUserAdmin, **admin_kwargs):
    user_admin = model_admin_cls()
    admin = Admin(model_admins=[user_admin], **admin_kwargs)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_bulk_action_runs_handler_over_selected_objects():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})
    b = user_admin.create({"email": "b@example.com", "is_active": True})
    user_admin.create({"email": "c@example.com", "is_active": True})

    response = client.post(
        "/admin/users/actions/deactivate",
        data={"pks": [str(a.id), str(b.id)]},
        follow_redirects=False,
        headers=csrf(client),
    )
    assert response.status_code == 303
    assert user_admin.get_object(a.id).is_active is False
    assert user_admin.get_object(b.id).is_active is False
    assert user_admin.get_object(3).is_active is True


def test_record_action_from_detail_page_selects_one_object():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})

    response = client.post(
        "/admin/users/actions/deactivate",
        data={"pks": [str(a.id)]},
        follow_redirects=False,
        headers=csrf(client),
    )
    assert response.status_code == 303
    assert user_admin.get_object(a.id).is_active is False


def test_bulk_action_with_no_selection_flashes_warning_and_skips_handler():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})

    response = client.post(
        "/admin/users/actions/deactivate", data={}, follow_redirects=False, headers=csrf(client)
    )
    assert response.status_code == 303
    assert user_admin.get_object(a.id).is_active is True  # handler never ran


def test_unknown_action_name_is_404():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})
    response = client.post(
        "/admin/users/actions/nonexistent", data={"pks": [str(a.id)]}, headers=csrf(client)
    )
    assert response.status_code == 404


def test_action_route_not_registered_when_no_actions_declared():
    client, _ = make_client(model_admin_cls=InMemoryUserAdmin)
    response = client.post("/admin/users/actions/deactivate", data={"pks": ["1"]})
    assert response.status_code == 404


def test_action_requires_extra_permission_when_declared():
    class DenyDeactivateAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "users.deactivate"

    client, user_admin = make_client(
        authenticator=AllowAllAuthenticator(), authorizer=DenyDeactivateAuthorizer()
    )

    class PermissionedUserAdmin(InMemoryUserAdmin):
        actions = [Action("deactivate", _deactivate, permission="deactivate")]

    user_admin = PermissionedUserAdmin()
    admin = Admin(
        model_admins=[user_admin],
        authenticator=AllowAllAuthenticator(),
        authorizer=DenyDeactivateAuthorizer(),
    )
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    a = user_admin.create({"email": "a@example.com"})

    response = client.post(
        "/admin/users/actions/deactivate", data={"pks": [str(a.id)]}, headers=csrf(client)
    )
    assert response.status_code == 403
    assert user_admin.get_object(a.id).is_active is True


def test_list_view_shows_action_bar_and_checkboxes():
    client, user_admin = make_client()
    user_admin.create({"email": "a@example.com"})
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert 'id="bulk-actions-form"' in response.text
    assert "Deactivate" in response.text
    assert 'name="pks"' in response.text


def test_list_view_hides_action_bar_when_no_actions_declared():
    client, _ = make_client(model_admin_cls=InMemoryUserAdmin)
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert 'id="bulk-actions-form"' not in response.text


def test_action_bar_submits_on_select_with_no_apply_step():
    client, user_admin = make_client()
    user_admin.create({"email": "a@example.com"})
    response = client.get("/admin/users")
    text = response.text
    assert 'name="action_choice"' not in text
    assert ">Apply<" not in text
    assert 'role="listbox"' in text and 'role="option"' in text
    assert 'data-url="/admin/users/actions/deactivate"' in text


def test_detail_and_form_pages_share_the_same_page_shell():
    """Both record pages use ui("page"): a width-capped column centered
    on both axes, with the action bar pinned to the bottom so a long
    record scrolls underneath it instead of burying its own buttons."""
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})

    detail = client.get(f"/admin/users/{a.id}").text
    edit = client.get(f"/admin/users/{a.id}/edit").text
    for page in (detail, edit):
        assert "max-w-xl" in page, "expected the page to cap its width"
        assert "mx-auto my-auto" in page, "expected the content centered on both axes"
        assert "sticky bottom-0" in page, "expected the action bar pinned to the bottom"


def test_record_page_actions_sit_in_the_sticky_bar_not_the_scrolling_body():
    """The buttons must be outside the scrolling column -- if they drift
    back into it they scroll away on a long record, which is the whole
    thing the sticky bar exists to prevent."""
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})

    page = client.get(f"/admin/users/{a.id}/edit").text
    bar_at = page.find("sticky bottom-0")
    save_at = page.find("Save and continue editing")
    assert bar_at != -1 and save_at > bar_at, (
        "expected the Save buttons to render inside the sticky action bar"
    )
    # Outside #resource-form, so they need the form attribute to submit it.
    assert 'form="resource-form"' in page


def test_detail_page_buttons_come_after_the_record_not_before_it():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})

    page = client.get(f"/admin/users/{a.id}").text
    dl_at = page.find("<dl")
    edit_link_at = page.find("/edit\"")
    assert dl_at != -1 and edit_link_at != -1 and edit_link_at > dl_at, (
        f"expected the record (<dl>, at {dl_at}) to precede the Edit button (at {edit_link_at})"
    )


def test_detail_view_shows_record_action_button():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})
    response = client.get(f"/admin/users/{a.id}")
    assert response.status_code == 200
    assert "/admin/users/actions/deactivate" in response.text
    assert "Deactivate" in response.text


def test_detail_record_action_buttons_stretch_while_the_bar_is_stacked():
    # An action's <button> is a grandchild of the flex row (the <form>
    # posting it sits in between), so the row's align-items:stretch stops
    # at the form and the button needs w-full of its own to match the
    # full-width Edit link beside it below sm.
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})
    response = client.get(f"/admin/users/{a.id}")
    assert "w-full sm:w-auto" in response.text, (
        "expected the record-action button to stretch while the action bar is stacked"
    )


def test_form_error_swap_targets_the_wrapper_not_the_inner_form():
    """A validation error re-renders the whole form wrapper, so the swap
    has to replace the wrapper. It used to target the inner <form> with
    outerHTML, which nested a fresh wrapper inside the old one on every
    failed save -- duplicating the inline sections and the action bar."""
    client, _ = make_client()

    page = client.get("/admin/users/create").text
    assert 'hx-target="#resource-form-wrapper"' in page, (
        "swap must target the wrapper, since the error response is the whole wrapper"
    )

    error = client.post(
        "/admin/users/create", data={"email": ""}, headers={"HX-Request": "true", **csrf(client)}
    ).text
    # The response must be exactly one wrapper -- the element the swap
    # replaces -- so re-rendering it can never nest.
    assert error.count('id="resource-form-wrapper"') == 1
    assert error.lstrip().startswith('<div id="resource-form-wrapper"')
    assert error.count("Save and continue editing") == 1


def test_delete_button_only_appears_while_editing():
    """Delete belongs to the edit form only: there is nothing to delete
    while creating, and the detail page deliberately no longer offers
    it, so looking at a record can't put a destructive action one click
    away."""
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})
    delete_href = f"/admin/users/{a.id}/delete"

    assert delete_href in client.get(f"/admin/users/{a.id}/edit").text, (
        "expected the edit form to offer Delete"
    )
    assert delete_href not in client.get(f"/admin/users/{a.id}").text, (
        "expected the detail page not to offer Delete"
    )
    assert "/delete" not in client.get("/admin/users/create").text, (
        "expected the create form not to offer Delete -- there is no record yet"
    )


def test_delete_is_separated_from_the_save_buttons():
    """Delete sits alone on the left, Save/Cancel on the right, so the
    destructive action is never adjacent to the one people click by
    reflex."""
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com"})

    page = client.get(f"/admin/users/{a.id}/edit").text
    delete_at = page.find("/delete")
    group_at = page.find("sm:ml-auto")
    save_at = page.find("Save and continue editing")
    assert -1 not in (delete_at, group_at, save_at)
    assert delete_at < group_at < save_at, (
        f"expected Delete ({delete_at}) before the right-hand group ({group_at}) "
        f"wrapping Save ({save_at})"
    )


def test_delete_button_hidden_when_authorizer_denies_it():
    class DenyDeleteAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "users.delete"

    client, user_admin = make_client(authorizer=DenyDeleteAuthorizer())
    a = user_admin.create({"email": "a@example.com"})

    page = client.get(f"/admin/users/{a.id}/edit").text
    assert "/delete" not in page, "expected Delete to be omitted when the authorizer denies it"


def test_action_ignores_an_off_site_referer():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})
    headers = csrf(client)
    headers["referer"] = "https://evil.example.com/admin/users"

    response = client.post(
        "/admin/users/actions/deactivate",
        data={"pks": [str(a.id)]},
        headers=headers,
        follow_redirects=False,
    )
    assert response.headers["location"] == "/admin/users"


def test_action_keeps_an_on_site_referer():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})
    headers = csrf(client)
    headers["referer"] = "/admin/users?page=2"

    response = client.post(
        "/admin/users/actions/deactivate",
        data={"pks": [str(a.id)]},
        headers=headers,
        follow_redirects=False,
    )
    assert response.headers["location"] == "/admin/users?page=2"


# -- select all matching --------------------------------------------------


def test_select_all_matching_acts_on_every_filtered_row_not_just_the_page():
    # A checkbox can only reach the rows on screen, so before this an
    # action over a filtered set of 60 from a 25-row page was impossible
    # to express: the user ticked "all", got 25, and was told 25 records
    # were affected. The count was honest; the intent was not.
    client, user_admin = make_client()
    for i in range(60):
        user_admin.create({"email": f"user{i}@example.com", "is_active": True})

    response = client.post(
        "/admin/users/actions/deactivate",
        data={"_select_all": "1"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.status_code == 303
    for obj in user_admin.get_queryset():
        assert not obj.is_active, f"{obj.email} was left untouched"


def test_select_all_matching_honours_the_posted_filters():
    # "All matching" means matching what the user was looking at.
    #
    # The excluded record is *active* and the filter selects *inactive*
    # ones, so acting on everything would flip it and honouring the
    # filter leaves it alone -- the two outcomes differ, which an
    # excluded record that already looked like the action's result could
    # not show.
    class FilterableActionableUserAdmin(ActionableUserAdmin):
        filters = [BooleanFilter("is_active")]

    client, user_admin = make_client(model_admin_cls=FilterableActionableUserAdmin)
    untouched = user_admin.create({"email": "active@example.com", "is_active": True})
    for i in range(5):
        user_admin.create({"email": f"inactive{i}@example.com", "is_active": False})

    client.post(
        "/admin/users/actions/deactivate",
        data={"_select_all": "1", "filter[is_active]": "false"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert user_admin.get_object(untouched.id).is_active, (
        "the record outside the filter was acted on -- the filters were ignored"
    )


def test_no_selection_without_the_flag_still_acts_on_nothing():
    client, user_admin = make_client()
    a = user_admin.create({"email": "a@example.com", "is_active": True})

    client.post(
        "/admin/users/actions/deactivate",
        data={},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert user_admin.get_object(a.id).is_active, "an empty selection must not act on everything"
