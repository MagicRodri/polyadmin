from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.field import ForeignKeyField, ManyToManyField, StringField
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.relation import Relation
from polyadmin.fastapi.router import create_router


class Organization:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class User:
    def __init__(self, id, email, organization=None, teams=()):
        self.id = id
        self.email = email
        self.organization = organization
        self.teams = list(teams)


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
# teams reuses the organizations admin as its target -- the widget only
# cares that a relation resolves to (pk, label) pairs, not what the
# target models.
TEAMS_RELATION = Relation("teams", target="organizations", display_field="name")


class UserAdmin(ModelAdmin):
    model = User
    slug = "users"
    list_display = ["id", "email", "organization"]
    detail_fields = ["id", "email", "organization", "teams"]
    form_fields = ["email", "organization", "teams"]
    fields = [
        StringField("email", required=True),
        ForeignKeyField("organization", relation=ORG_RELATION),
        ManyToManyField("teams", relation=TEAMS_RELATION),
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
    # The plain (non-autocomplete) relation field is the shadcn Select
    # port (ui/select.html): a hidden input named after the field, and
    # each choice as a listbox option rather than an <option>.
    assert 'name="organization"' in response.text
    assert 'data-value="1" data-label="Acme"' in response.text


def test_edit_form_preselects_current_relation():
    client, _, user_admin, org_admin = make_client()
    acme = org_admin.create({"name": "Acme"})
    user_admin._store[1] = User(1, "john@example.com", organization=acme)
    user_admin._next_id = 2

    response = client.get("/admin/users/1/edit")
    assert response.status_code == 200
    # Hidden input carries the pk; the trigger's initial label text is
    # the target's own label, not an <option selected>.
    assert f'name="organization" x-ref="hiddenInput" value="{acme.id}"' in response.text
    assert "Acme" in response.text


class AutocompleteUserAdmin(UserAdmin):
    autocomplete_fields = ["organization"]
    # Drop the many-to-many: it targets the same admin and renders every
    # option inline (that is what a multi-select is), which would defeat
    # the "an autocomplete field never dumps its target's queryset into
    # the page" assertion these fixtures exist to make.
    form_fields = ["email", "organization"]


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


# -- many-to-many: the searchable multi-select --------------------------


def multi_select_markup(page):
    """Just the multi-select component's markup: from its x-data to the
    next component's, so an assertion about this control can neither be
    satisfied nor broken by a sibling field."""
    marker = 'x-data="adminMultiSelect()"'
    start = page.index(marker) + len(marker)
    rest = page[start:]
    end = rest.find("x-data=")
    return rest if end < 0 else rest[:end]


def test_many_to_many_renders_searchable_multi_select_not_a_native_multiple():
    client, _, _, org_admin = make_client()
    org_admin.create({"name": "Acme"})
    org_admin.create({"name": "Widgets Inc"})

    text = client.get("/admin/users/create").text

    assert "<select multiple" not in text, "expected the native <select multiple> to be gone"
    assert 'x-data="adminMultiSelect()"' in text, "expected the multi-select component"
    # The list is "what you can still add": a chosen option leaves it for
    # a chip, so nothing in it is ever in a selected state -- no check
    # indicator, and no aria-selected to carry.
    assert 'x-show="available($el)"' in text, "expected the list to hide options once chosen"
    # Scoped to the multi-select's own markup: this form also renders a
    # ui/select for the foreign key, and that one carries aria-selected
    # legitimately (its list does show a chosen option).
    ms = multi_select_markup(text)
    assert "aria-selected" not in ms and "aria-multiselectable" not in ms, (
        "expected no selected-state ARIA on a list that never shows selected options"
    )
    # Every option is in the page -- a many-to-many's list is already
    # fully rendered, which is what lets the search filter client-side.
    for want in ('data-value="1"', 'data-value="2"', "Acme", "Widgets Inc"):
        assert want in text, f"expected option {want!r} in the page"
    assert 'placeholder="Search&hellip;"' in text, "expected the search box"


# The widget posts what a <select multiple> posted: repeated inputs under
# the field's own name, which is what parse_form_data's getlist reads.
def test_many_to_many_selection_posts_under_the_field_name():
    client, _, user_admin, org_admin = make_client()
    org_admin.create({"name": "Acme"})
    widgets = org_admin.create({"name": "Widgets Inc"})
    user_admin._store[1] = User(1, "john@example.com", teams=[widgets])

    text = client.get("/admin/users/1/edit").text

    assert '<input type="hidden" name="teams"' in text
    # The current selection is marked on the option, which is what the
    # component hydrates its initial state from.
    assert 'data-value="2" data-label="Widgets Inc" data-selected="true"' in text
    assert 'data-value="1" data-label="Acme" data-selected="true"' not in text


# The multi-select declares role=combobox/listbox, which promises
# assistive tech that the keyboard works. Focus stays in the search box
# -- typing is the point of this control -- so the arrows move an
# aria-activedescendant highlight rather than real focus.
def test_multi_select_is_keyboard_operable():
    client, _, _, org_admin = make_client()
    org_admin.create({"name": "Acme"})
    ms = multi_select_markup(client.get("/admin/users/create").text)

    for want in (
        '@keydown.down.prevent="move(1)"',
        '@keydown.up.prevent="move(-1)"',
        '@keydown.enter.prevent="chooseActive()"',
        ':aria-activedescendant="activeId || null"',
        'role="combobox"',
    ):
        assert want in ms, f"multi-select is missing {want!r}"
    assert 'role="option" tabindex="0"' not in ms, (
        "options must not be individually tabbable -- the search box holds focus"
    )


# The autocomplete relation field is the fourth listbox in the tree. It
# always had arrow keys, but announced nothing: no combobox role and no
# way for a screen reader to know which result was highlighted.
def test_relation_combobox_is_announced_to_assistive_tech():
    # _make_autocomplete_client, not make_client: the plain fixture
    # renders a ui/select for the relation and a multi-select for the
    # m2m, both of which carry these same attributes -- the assertions
    # below would pass without the combobox being on the page at all.
    client, _, org_admin = _make_autocomplete_client()
    org_admin.create({"name": "Acme"})
    page = client.get("/admin/users/create").text

    assert "adminMultiSelect()" not in page and "adminSelect()" not in page, (
        "fixture leaked another listbox onto the page; these assertions would be vacuous"
    )
    for want in (
        'role="combobox"',
        'aria-autocomplete="list"',
        ':aria-activedescendant="activeId || null"',
        'role="listbox"',
        # A swap replaces the results, so the remembered highlight has to
        # be dropped or activeId names a detached node.
        '@htmx:after-swap="clearActive()"',
    ):
        assert want in page, f"relation combobox is missing {want!r}"


def test_lookup_results_are_listbox_options():
    client, _, org_admin = _make_autocomplete_client()
    org_admin.create({"name": "Acme"})

    fragment = client.get("/admin/organizations/lookup?q=acme").text
    assert 'role="option"' in fragment, (
        "lookup results must be options, or the panel is a listbox with no options in it"
    )
