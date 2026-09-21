import asyncio

from polyadmin.core.field import ForeignKeyField, StringField
from polyadmin.core.inline import (
    Inline,
    StackedInline,
    TabularInline,
    afilter_inline_children,
    filter_inline_children,
)
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


class _Parent:
    def __init__(self, id):
        self.id = id


class _Child:
    def __init__(self, id, parent):
        self.id = id
        self.parent = parent


class _ParentAdmin(ModelAdmin):
    model = _Parent
    slug = "parents"
    fields = []


_PARENT_FIELD = ForeignKeyField("parent", relation=Relation("parent", target="parents"))


def test_afilter_asks_a_list_page_child_for_the_parents_rows():
    seen = []

    class PageChildAdmin(ModelAdmin):
        model = _Child
        slug = "children"
        fields = [_PARENT_FIELD]

        async def list_page(self, list_request):
            seen.append((dict(list_request.filters), list_request.unlimited))
            return [_Child(7, None), _Child(8, None)], 2

    result = asyncio.run(afilter_inline_children(PageChildAdmin(), "parent", _ParentAdmin(), 5))

    assert seen == [({"parent": "5"}, True)]
    # The child answered for the filter, so its rows are used as returned.
    assert [c.id for c in result] == [7, 8]


def test_afilter_filters_an_async_get_queryset_child_in_memory():
    class AsyncQuerysetChildAdmin(ModelAdmin):
        model = _Child
        slug = "children"
        fields = [_PARENT_FIELD]

        async def get_queryset(self):
            return [_Child(1, _Parent(5)), _Child(2, _Parent(6)), _Child(3, None)]

    result = asyncio.run(afilter_inline_children(AsyncQuerysetChildAdmin(), "parent", _ParentAdmin(), "5"))

    assert [c.id for c in result] == [1]
