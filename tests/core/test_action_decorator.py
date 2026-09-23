"""@action: declaring actions as ModelAdmin methods."""

import asyncio
from collections.abc import Sequence

import pytest

from polyadmin.core.action import DELETE_SELECTED_NAME, action
from polyadmin.core.auth import Principal
from tests.core.test_model_admin import InMemoryUserAdmin, User


def names(actions):
    return [a.name for a in actions]


def by_name(model_admin):
    return {a.name: a for a in model_admin.get_actions()}


def test_the_decorator_returns_the_function_unchanged():
    def method(self, objects, principal):
        return None

    assert action(method) is method
    assert action(label="Label")(method) is method


def test_bare_and_called_forms_both_register_an_action():
    class Users(InMemoryUserAdmin):
        @action
        def bare(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return None

        @action(label="Called", confirm="Sure?", permission="called", where="detail")
        def called(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return None

    found = by_name(Users())
    assert (found["bare"].label, found["bare"].confirm, found["bare"].permission, found["bare"].where) == (
        "Bare",
        None,
        None,
        "both",
    )
    assert (found["called"].label, found["called"].confirm, found["called"].permission, found["called"].where) == (
        "Called",
        "Sure?",
        "called",
        "detail",
    )


def test_the_default_label_title_cases_the_method_name():
    class Users(InMemoryUserAdmin):
        @action
        def send_welcome_email(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return None

    assert by_name(Users())["send_welcome_email"].label == "Send Welcome Email"


def test_an_invalid_where_fails_when_the_class_body_runs():
    with pytest.raises(ValueError, match="sidebar"):

        @action(where="sidebar")  # type: ignore[arg-type]
        def method(self, objects, principal):
            return None


def test_the_handler_is_the_bound_method():
    class Users(InMemoryUserAdmin):
        @action
        def touch(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return f"touched {len(objects)} via {type(self).__name__}"

    assert Users().get_action("touch").handler([1, 2], None) == "touched 2 via Users"


class Base(InMemoryUserAdmin):
    @action(label="Ping", confirm="Ping them?")
    def ping(self, objects: Sequence[User], principal: Principal | None) -> str | None:
        return "base"

    @action
    def other(self, objects: Sequence[User], principal: Principal | None) -> str | None:
        return "base"


def test_actions_keep_definition_order_with_delete_selected_last():
    assert names(Base().get_actions()) == ["ping", "other", DELETE_SELECTED_NAME]


def test_a_subclass_inherits_actions_base_first():
    class Child(Base):
        @action
        def extra(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return None

    assert names(Child().get_actions()) == ["ping", "other", "extra", DELETE_SELECTED_NAME]


def test_overriding_without_redecorating_keeps_the_base_options_and_runs_the_override():
    class Child(Base):
        def ping(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return "child"

    child = Child()
    ping = child.get_action("ping")
    assert (ping.label, ping.confirm) == ("Ping", "Ping them?")
    assert ping.handler([], None) == "child"
    assert names(child.get_actions()).count("ping") == 1


def test_overriding_with_redecorating_replaces_the_options_and_keeps_the_position():
    class Child(Base):
        @action(label="Ring")
        def ping(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return "child"

    actions = Child().get_actions()
    assert names(actions) == ["ping", "other", DELETE_SELECTED_NAME]
    ping = next(a for a in actions if a.name == "ping")
    assert (ping.label, ping.confirm) == ("Ring", None)


def test_the_old_actions_attribute_raises_a_type_error_naming_the_class():
    with pytest.raises(TypeError, match="StaleAdmin"):

        class StaleAdmin(InMemoryUserAdmin):
            actions = []


def test_delete_selected_is_a_list_only_action_on_every_admin():
    built_in = InMemoryUserAdmin().get_action(DELETE_SELECTED_NAME)
    assert built_in.where == "list"
    assert built_in.permission == "delete"
    assert built_in.label == "Delete selected"
    assert built_in.confirm


def test_delete_selected_goes_away_when_disabled_or_delete_is_off():
    class Opted(InMemoryUserAdmin):
        disable_delete_selected = True

    class NoDelete(InMemoryUserAdmin):
        can_delete = False

    class OverriddenButDisabled(InMemoryUserAdmin):
        disable_delete_selected = True

        def delete_selected(self, objects, principal):
            return "mine"

    for cls in (Opted, NoDelete, OverriddenButDisabled):
        assert DELETE_SELECTED_NAME not in names(cls().get_actions())


def test_overriding_delete_selected_replaces_the_deletion_and_keeps_the_rest():
    class Users(InMemoryUserAdmin):
        def delete_selected(self, objects: Sequence[User], principal: Principal | None) -> str | None:
            return "mine ran"

    replaced = Users().get_action(DELETE_SELECTED_NAME)
    assert replaced.handler([], None) == "mine ran"
    assert (replaced.permission, replaced.where) == ("delete", "list")


def test_delete_selected_deletes_through_the_delete_hook():
    model_admin = InMemoryUserAdmin()
    user = model_admin.create({"email": "a@example.com"})
    message = asyncio.run(model_admin.delete_selected([user], None))
    assert model_admin.get_object(user.id) is None
    assert "1" in message
