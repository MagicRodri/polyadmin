"""The delete-preview capability and its resolution (docs/deletes.md)."""

from dataclasses import dataclass

import pytest

from polyadmin.core.admin import Admin
from polyadmin.core.delete import (
    DELETE_PREVIEW_SAMPLE,
    DeleteGroup,
    DeletePreview,
    previews_deletes,
    resolve_delete_preview,
    selection_fingerprint,
)
from polyadmin.core.model_admin import ModelAdmin


@dataclass
class Item:
    id: int
    name: str

    def __str__(self):
        return f"item {self.name}"


@dataclass
class User:
    id: int
    name: str


@dataclass
class Invoice:
    id: int
    name: str


@dataclass
class Organization:
    id: int
    name: str


class UserAdmin(ModelAdmin):
    model = User
    list_display = ["id", "name"]


class InvoiceAdmin(ModelAdmin):
    model = Invoice
    list_display = ["id", "name"]


class OrganizationAdmin(ModelAdmin):
    model = Organization
    list_display = ["id", "name"]

    def __init__(self):
        super().__init__()
        self.preview = DeletePreview()
        self.error = None
        self.calls = 0
        self.got = None

    def delete_preview(self, objects):
        self.calls += 1
        self.got = objects
        if self.error:
            raise self.error
        return self.preview


def items(*names):
    return [Item(id=i + 1, name=n) for i, n in enumerate(names)]


def setup(authorizer=None, *extra):
    source = OrganizationAdmin()
    admin = Admin(model_admins=[source, UserAdmin(), InvoiceAdmin(), *extra], authorizer=authorizer)
    return admin, source


class Deny:
    def __init__(self, rule):
        self.rule = rule

    def can(self, principal, permission, resource):
        return self.rule(permission, resource)


def test_no_capability_resolves_to_nothing():
    plain = UserAdmin()
    admin = Admin(model_admins=[plain])
    got = resolve_delete_preview(admin, plain, None, items("a"))
    assert not got.blocked and not got.cascades and not got.protected
    assert not previews_deletes(plain)


def test_resolve_calls_the_host_once_with_the_objects():
    admin, source = setup()
    objs = items("acme")
    resolve_delete_preview(admin, source, None, objs)
    assert source.calls == 1 and source.got == objs
    assert previews_deletes(source)


def test_cascade_group_is_sampled_and_counted():
    admin, source = setup()
    source.preview = DeletePreview(cascades=[DeleteGroup(resource="users", objects=items(*"abcdefghijkl"), total=40)])
    g = resolve_delete_preview(admin, source, None, items("acme")).cascades[0]
    assert (g.label, g.total, len(g.visible), g.more, g.hidden) == ("User", 40, DELETE_PREVIEW_SAMPLE, 30, 0)
    assert g.model_admin.get_slug() == "users"


def test_total_is_raised_to_the_sample_and_empty_groups_are_dropped():
    admin, source = setup()
    source.preview = DeletePreview(
        cascades=[DeleteGroup(resource="users", objects=items("a", "b")), DeleteGroup(resource="invoices")],
        protected=[DeleteGroup(resource="invoices", total=0)],
    )
    got = resolve_delete_preview(admin, source, None, items("acme"))
    assert [(g.total, g.more) for g in got.cascades] == [(2, 0)]
    assert not got.protected and not got.blocked


def test_host_label_wins_and_unmanaged_types_render_as_text():
    admin, source = setup()
    source.preview = DeletePreview(
        cascades=[
            DeleteGroup(resource="users", label="Members", objects=items("a")),
            DeleteGroup(label="Sessions", objects=items("s1", "s2")),
        ]
    )
    got = resolve_delete_preview(admin, source, None, items("acme"))
    assert got.cascades[0].label == "Members"
    unmanaged = got.cascades[1]
    assert unmanaged.model_admin is None and unmanaged.texts == ["item s1", "item s2"] and not unmanaged.visible


@pytest.mark.parametrize("group", [DeleteGroup(objects=items("a")), DeleteGroup(resource="ghosts", objects=items("a"))])
def test_groups_need_a_resource_or_a_label_and_a_known_slug(group):
    admin, source = setup()
    source.preview = DeletePreview(cascades=[group])
    with pytest.raises(ValueError):
        resolve_delete_preview(admin, source, None, items("acme"))


def test_host_error_propagates():
    admin, source = setup()
    source.error = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        resolve_delete_preview(admin, source, None, items("acme"))


def test_records_the_principal_cannot_view_are_counted_not_named():
    deny = Deny(lambda permission, resource: not (permission == "users.view" and getattr(resource, "name", "") == "secret"))
    admin, source = setup(deny)
    source.preview = DeletePreview(cascades=[DeleteGroup(resource="users", objects=items("open", "secret"))])
    g = resolve_delete_preview(admin, source, None, items("acme")).cascades[0]
    assert [o.name for o in g.visible] == ["open"] and g.hidden == 1


def test_protected_records_block():
    admin, source = setup()
    source.preview = DeletePreview(protected=[DeleteGroup(resource="invoices", objects=items("inv"))])
    got = resolve_delete_preview(admin, source, None, items("acme"))
    assert got.blocked and len(got.protected) == 1 and not got.denied_types


def test_cascade_into_a_type_the_principal_cannot_delete_blocks():
    admin, source = setup(Deny(lambda permission, resource: permission != "users.delete"))
    source.preview = DeletePreview(
        cascades=[DeleteGroup(resource="users", objects=items("a")), DeleteGroup(label="Sessions", objects=items("s"))]
    )
    got = resolve_delete_preview(admin, source, None, items("acme"))
    assert got.blocked and got.denied_types == ["User"]


def test_cascade_into_a_type_with_delete_disabled_blocks():
    @dataclass
    class Ledger:
        id: int
        name: str

    class LedgerAdmin(ModelAdmin):
        model = Ledger
        list_display = ["id", "name"]
        can_delete = False

    admin, source = setup(None, LedgerAdmin())
    source.preview = DeletePreview(cascades=[DeleteGroup(resource="ledgers", objects=items("l"))])
    got = resolve_delete_preview(admin, source, None, items("acme"))
    assert got.blocked and got.denied_types == ["Ledger"]


def test_selection_fingerprint_is_sorted_and_stable():
    objs = [Item(id=2, name=""), Item(id=10, name=""), Item(id=1, name="")]
    # sha256("1\n10\n2"): the Go implementation asserts the same literal.
    assert selection_fingerprint(UserAdmin(), objs) == "32d5c2d95a5bef8b0f13c335628b73422fa80b6eba491f32520f57a395c464bb"
