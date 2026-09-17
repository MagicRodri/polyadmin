"""sortable_by and list_display_links on the rendered list (docs/lists.md)."""

from datetime import date
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin import DateField
from polyadmin.core.admin import Admin
from polyadmin.core.filter import DateFilter
from polyadmin.fastapi.router import create_router
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin
from tests.fastapi import test_inlines as inl


def client_for(admin_cls, emails=("a@example.com",)):
    users = admin_cls()
    for email in emails:
        users.create({"email": email})
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_a_non_sortable_column_has_no_sort_menu():
    class Restricted(InMemoryUserAdmin):
        sortable_by = ["email"]

    page = client_for(Restricted).get("/admin/users").text
    assert "sort=email" in page
    assert "sort=is_active" not in page and "sort=-is_active" not in page


def test_every_sort_menu_survives_when_sortable_by_is_unset():
    page = client_for(InMemoryUserAdmin).get("/admin/users").text
    for want in ("sort=email", "sort=is_active", "sort=id"):
        assert want in page, want


def test_the_first_cell_links_to_the_record_by_default():
    page = client_for(InMemoryUserAdmin).get("/admin/users").text
    # The cell links to the record, carrying the list it came from.
    assert '<a href="/admin/users/1?_list=' in page
    # The cell link plus the row menu's View, and nothing else.
    assert page.count('href="/admin/users/1?_list=') == 2


def test_list_display_links_moves_the_link_and_empty_removes_it():
    class Linked(InMemoryUserAdmin):
        list_display_links = ["email"]

    page = client_for(Linked).get("/admin/users").text
    assert '<a href="/admin/users/1?_list=' in page and "a@example.com</a>" in page

    class Unlinked(InMemoryUserAdmin):
        list_display_links = []

    page = client_for(Unlinked).get("/admin/users").text
    assert page.count('href="/admin/users/1?_list=') == 1  # only the row menu's View


def test_a_cell_that_is_already_a_link_is_not_wrapped_again():
    org_store, user_store = {}, {}
    org_admin = inl.make_organization_admin()(org_store)

    class RelationFirstUserAdmin(inl.UserAdmin):
        list_display = ["organization", "email"]
        list_display_links = ["organization"]

    user_admin = RelationFirstUserAdmin(user_store, org_store)
    app = FastAPI()
    app.include_router(
        create_router(Admin(model_admins=[org_admin, user_admin]), base_path="/admin"), prefix="/admin"
    )
    client = TestClient(app)
    inl.seed_org_with_users(org_admin, user_admin, "a@example.com")

    page = client.get("/admin/users").text
    assert 'class="text-primary underline-offset-4 hover:underline"><a' not in page
    assert 'href="/admin/organizations/1"' in page


# --- preserve_filters ------------------------------------------------

# The list URL the tests navigate away from and expect to come back to.
FILTERED_LIST = "/admin/users?search=a&sort=-email"
FILTERED_TOKEN = quote(FILTERED_LIST, safe="")


def test_list_links_carry_the_list_they_came_from():
    page = client_for(InMemoryUserAdmin).get(FILTERED_LIST).text
    for want in (
        "/admin/users/1?_list=",
        "/admin/users/1/edit?_list=",
        "/admin/users/1/delete?_list=",
        "/admin/users/create?_list=",
    ):
        assert want in page, want
    assert "search%3Da" in page


def test_disabling_preserve_filters_drops_the_token():
    class Bare(InMemoryUserAdmin):
        preserve_filters = False

    assert "_list=" not in client_for(Bare).get(FILTERED_LIST).text


def test_the_breadcrumb_leads_back_into_the_filtered_list():
    client = client_for(InMemoryUserAdmin)
    for path in (
        f"/admin/users/1?_list={FILTERED_TOKEN}",
        f"/admin/users/1/edit?_list={FILTERED_TOKEN}",
        f"/admin/users/1/delete?_list={FILTERED_TOKEN}",
    ):
        assert 'href="/admin/users?search=a&amp;sort=-email"' in client.get(path).text, path


def test_saving_returns_to_the_list_it_came_from():
    client = client_for(InMemoryUserAdmin)
    page = client.get(f"/admin/users/1/edit?_list={FILTERED_TOKEN}").text
    assert 'name="_list" value="/admin/users?search=a&amp;sort=-email"' in page

    response = client.post(
        "/admin/users/1/edit",
        data={"email": "a@example.com", "is_active": "on", "_list": FILTERED_LIST},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.headers["location"] == f"/admin/users/1?_list={FILTERED_TOKEN}"


def test_save_and_add_another_keeps_the_list():
    client = client_for(InMemoryUserAdmin)
    response = client.post(
        "/admin/users/create",
        data={"email": "b@example.com", "is_active": "on", "_addanother": "1", "_list": FILTERED_LIST},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.headers["location"] == f"/admin/users/create?_list={FILTERED_TOKEN}"


def test_deleting_returns_to_the_filtered_list():
    client = client_for(InMemoryUserAdmin)
    response = client.post(
        "/admin/users/1/delete", data={"_list": FILTERED_LIST}, headers=csrf(client), follow_redirects=False
    )
    assert response.headers["location"] == FILTERED_LIST


def test_an_offsite_list_token_is_discarded():
    client = client_for(InMemoryUserAdmin)
    response = client.post(
        "/admin/users/1/delete",
        data={"_list": "https://evil.example/admin/users"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.headers["location"] == "/admin/users"


# --- save_as ---------------------------------------------------------


class SaveAsUserAdmin(InMemoryUserAdmin):
    save_as = True


def test_save_as_new_appears_only_on_the_edit_form_and_only_when_allowed():
    client = client_for(SaveAsUserAdmin)
    assert 'name="_saveasnew"' in client.get("/admin/users/1/edit").text
    assert 'name="_saveasnew"' not in client.get("/admin/users/create").text
    assert 'name="_saveasnew"' not in client_for(InMemoryUserAdmin).get("/admin/users/1/edit").text


def test_save_as_new_creates_a_copy_and_leaves_the_original():
    users = SaveAsUserAdmin()
    users.create({"email": "a@example.com"})
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    response = client.post(
        "/admin/users/1/edit",
        data={"email": "copy@example.com", "is_active": "on", "_saveasnew": "1"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert len(users.get_queryset()) == 2
    assert users.get_object(1).email == "a@example.com"
    assert users.get_object(2).email == "copy@example.com"
    # The redirect lands on the new record, which is where a create lands.
    assert response.headers["location"] == "/admin/users/2"


def test_save_as_new_is_an_ordinary_save_when_the_option_is_off():
    users = InMemoryUserAdmin()
    users.create({"email": "a@example.com"})
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    client.post(
        "/admin/users/1/edit",
        data={"email": "renamed@example.com", "is_active": "on", "_saveasnew": "1"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert len(users.get_queryset()) == 1
    assert users.get_object(1).email == "renamed@example.com"


def test_save_as_new_redisplays_the_form_on_a_validation_error():
    users = SaveAsUserAdmin()
    users.create({"email": "a@example.com"})
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    response = client.post(
        "/admin/users/1/edit",
        data={"email": "", "is_active": "on", "_saveasnew": "1"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert len(users.get_queryset()) == 1


# --- prepopulated_fields ---------------------------------------------


def test_prepopulated_fields_ride_on_the_create_form_only():
    class Prepopulating(InMemoryUserAdmin):
        prepopulated_fields = {"email": ["email"]}

    client = client_for(Prepopulating)
    create = client.get("/admin/users/create").text
    assert "data-prepopulated=" in create and "email" in create
    # An existing record's slug is a real identifier; it is never rewritten.
    assert "data-prepopulated=" not in client.get("/admin/users/1/edit").text


def test_no_prepopulation_attribute_without_the_option():
    assert "data-prepopulated=" not in client_for(InMemoryUserAdmin).get("/admin/users/create").text


def test_prepopulated_unicode_fields_are_marked():
    class UnicodeSlug(InMemoryUserAdmin):
        prepopulated_fields = {"email": ["email"]}
        prepopulated_unicode = ["email"]

    assert "unicode" in client_for(UnicodeSlug).get("/admin/users/create").text


# --- the date filter -------------------------------------------------


class DatedUserAdmin(InMemoryUserAdmin):
    """Declares a DateFilter over its own date field, as an application would."""

    list_display = ["id", "email", "joined"]
    fields = [*InMemoryUserAdmin.fields, DateField("joined")]
    filters = [DateFilter("joined")]


def dated_client(*joins):
    users = DatedUserAdmin()
    for email, joined in joins:
        users.create({"email": email}).joined = joined
    app = FastAPI()
    app.include_router(create_router(Admin(model_admins=[users]), base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_the_date_filter_renders_in_the_filter_panel():
    page = dated_client(("a@example.com", date.today())).get("/admin/users").text  # noqa: DTZ011
    # One entry in the panel, with the presets as its choices -- exactly
    # how a boolean or choice filter renders.
    for want in ("Joined", "Any date", "Today", "Past 7 days", "This month", "This year"):
        assert want in page, want
    assert "filter%5Bjoined%5D=today" in page
    # And nothing above the table.
    assert "All dates" not in page


def test_the_date_filter_narrows_the_rows():
    client = dated_client(
        ("recent@example.com", date.today()),  # noqa: DTZ011
        ("old@example.com", date.today().replace(year=date.today().year - 2)),  # noqa: DTZ011
    )
    page = client.get("/admin/users?filter[joined]=year").text
    assert "recent@example.com" in page and "old@example.com" not in page


def test_no_date_filter_unless_declared():
    assert "Any date" not in client_for(InMemoryUserAdmin).get("/admin/users").text
