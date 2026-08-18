from polyadmin.core.field import ForeignKeyField, StringField
from polyadmin.core.inline import Inline, StackedInline, TabularInline, filter_inline_children
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.relation import Relation

ORGANIZATION_RELATION = Relation("organization", target="organizations", display_field="name")


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

    def __init__(self, orgs):
        super().__init__()
        self._orgs = orgs

    def get_queryset(self):
        return self._orgs


class UserAdmin(ModelAdmin):
    model = User
    slug = "users"
    list_display = ["id", "email", "organization"]
    form_fields = ["email", "organization"]
    fields = [
        StringField("email", required=True),
        ForeignKeyField("organization", relation=ORGANIZATION_RELATION),
    ]

    def __init__(self, users):
        super().__init__()
        self._users = users

    def get_queryset(self):
        return self._users


def test_inline_defaults():
    inline = Inline("users", "organization")
    assert inline.child == "users"
    assert inline.fk_field == "organization"
    assert inline.layout == "stacked"
    assert inline.label is None


def test_stacked_inline_sets_layout():
    inline = StackedInline("users", "organization")
    assert inline.layout == "stacked"


def test_tabular_inline_sets_layout():
    inline = TabularInline("users", "organization")
    assert inline.layout == "tabular"


def test_inline_label_can_be_overridden():
    inline = Inline("users", "organization", label="Members")
    assert inline.label == "Members"


def test_filter_inline_children_matches_by_parent_pk():
    acme = Organization(1, "Acme")
    widgets = Organization(2, "Widgets")
    users = [
        User(1, "a@example.com", organization=acme),
        User(2, "b@example.com", organization=widgets),
        User(3, "c@example.com", organization=acme),
    ]
    org_admin = OrganizationAdmin([acme, widgets])
    user_admin = UserAdmin(users)

    result = filter_inline_children(user_admin, "organization", org_admin, acme.id)

    assert [u.email for u in result] == ["a@example.com", "c@example.com"]


def test_filter_inline_children_no_match_returns_empty():
    acme = Organization(1, "Acme")
    users = [User(1, "a@example.com", organization=acme)]
    org_admin = OrganizationAdmin([acme])
    user_admin = UserAdmin(users)

    assert filter_inline_children(user_admin, "organization", org_admin, 999) == []


def test_filter_inline_children_skips_unset_fk():
    acme = Organization(1, "Acme")
    users = [User(1, "a@example.com", organization=None)]
    org_admin = OrganizationAdmin([acme])
    user_admin = UserAdmin(users)

    assert filter_inline_children(user_admin, "organization", org_admin, acme.id) == []


def test_filter_inline_children_compares_pks_as_strings():
    acme = Organization(1, "Acme")
    users = [User(1, "a@example.com", organization=acme)]
    org_admin = OrganizationAdmin([acme])
    user_admin = UserAdmin(users)

    # parent_pk passed as a string (as it would arrive from a URL path
    # param) must still match the int id stored on the object.
    result = filter_inline_children(user_admin, "organization", org_admin, "1")
    assert len(result) == 1
