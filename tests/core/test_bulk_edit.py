import asyncio

import pytest

from polyadmin.core.action import BULK_EDIT_NAME, DELETE_SELECTED_NAME, action
from polyadmin.core.admin import Admin
from tests.core.test_model_admin import InMemoryUserAdmin


class BulkUserAdmin(InMemoryUserAdmin):
    bulk_edit_fields = ("is_active",)


def test_no_bulk_edit_action_without_fields():
    assert InMemoryUserAdmin().get_action(BULK_EDIT_NAME) is None


def test_bulk_edit_action_is_offered_on_the_list_before_delete_selected():
    names = [a.name for a in BulkUserAdmin().get_list_actions()]
    assert names[-2:] == [BULK_EDIT_NAME, DELETE_SELECTED_NAME]


def test_bulk_edit_form_uses_the_model_admins_own_fields():
    ma = BulkUserAdmin()
    (field,) = ma.get_action(BULK_EDIT_NAME).form
    assert field is ma.get_field("is_active")


def test_bulk_edit_requires_update_permission_and_can_update():
    ma = BulkUserAdmin()
    assert ma.get_action(BULK_EDIT_NAME).permission == "update"

    class ReadOnlyAdmin(BulkUserAdmin):
        can_update = False

    assert ReadOnlyAdmin().get_action(BULK_EDIT_NAME) is None


def test_bulk_edit_is_never_a_detail_action():
    class Named(BulkUserAdmin):
        detail_actions = [BULK_EDIT_NAME]

    assert Named().get_detail_actions() == []


def test_unknown_bulk_edit_field_is_rejected_on_register():
    class Bad(InMemoryUserAdmin):
        bulk_edit_fields = ("nope",)

    with pytest.raises(ValueError, match="nope"):
        Admin(model_admins=[Bad()])


def test_readonly_bulk_edit_field_is_rejected_on_register():
    class Bad(InMemoryUserAdmin):
        bulk_edit_fields = ("email",)
        readonly_fields = ("email",)

    with pytest.raises(ValueError, match="read-only"):
        Admin(model_admins=[Bad()])


def test_default_bulk_update_calls_update_with_only_the_given_data():
    ma = BulkUserAdmin()
    a = ma.create({"email": "a@example.com", "is_active": True})
    b = ma.create({"email": "b@example.com", "is_active": True})
    message = asyncio.run(ma.bulk_update([a, b], {"is_active": False}, None))
    assert (a.is_active, b.is_active) == (False, False)
    assert (a.email, b.email) == ("a@example.com", "b@example.com")
    assert message == "Updated 2 records."


def test_default_bulk_update_reports_progress_on_failure():
    class Failing(BulkUserAdmin):
        def update(self, obj, data):
            if obj.id == 2:
                raise RuntimeError("boom")
            return super().update(obj, data)

    ma = Failing()
    a = ma.create({"email": "a@example.com"})
    b = ma.create({"email": "b@example.com"})
    with pytest.raises(RuntimeError, match="Updated 1 of 2, then failed: boom"):
        asyncio.run(ma.bulk_update([a, b], {"is_active": False}, None))


def test_overriding_bulk_edit_replaces_the_builtin():
    class Custom(BulkUserAdmin):
        @action(label="Mass edit", form=lambda ma: ma.get_bulk_edit_form(), permission="update", where="list")
        async def bulk_edit(self, objects, principal, data):
            return "custom"

    assert Custom().get_action(BULK_EDIT_NAME).label == "Mass edit"
