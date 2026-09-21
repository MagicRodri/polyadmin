"""Where an action appears: the list page, the detail page, or both."""

import pytest

from polyadmin.core.action import DELETE_SELECTED_NAME, Action
from polyadmin.core.admin import Admin
from tests.core.test_model_admin import InMemoryUserAdmin


def _noop(model_admin, objects, principal):
    return None


def names(actions):
    return [a.name for a in actions]


def make(**attrs):
    return type("Users", (InMemoryUserAdmin,), attrs)()


def test_where_defaults_to_both():
    assert Action("x", _noop).where == "both"


def test_where_rejects_unknown_values():
    with pytest.raises(ValueError):
        Action("x", _noop, where="sidebar")


def test_delete_selected_is_list_only():
    built_in = next(a for a in make().get_actions() if a.name == DELETE_SELECTED_NAME)
    assert built_in.where == "list"


def test_default_placement_follows_where():
    ma = make(
        actions=[
            Action("both", _noop),
            Action("only_list", _noop, where="list"),
            Action("only_detail", _noop, where="detail"),
        ]
    )
    assert names(ma.get_list_actions()) == ["both", "only_list", DELETE_SELECTED_NAME]
    assert names(ma.get_detail_actions()) == ["both", "only_detail"]


def test_delete_selected_never_reaches_the_detail_page():
    assert DELETE_SELECTED_NAME not in names(make().get_detail_actions())


def test_detail_actions_is_an_ordered_allowlist_that_overrides_where():
    ma = make(
        actions=[Action("a", _noop), Action("b", _noop, where="list"), Action("c", _noop)],
        detail_actions=["c", "b"],
    )
    assert names(ma.get_detail_actions()) == ["c", "b"]
    # The list page is unaffected by detail_actions.
    assert names(ma.get_list_actions()) == ["a", "b", "c", DELETE_SELECTED_NAME]


def test_empty_detail_actions_means_none():
    ma = make(actions=[Action("a", _noop)], detail_actions=[])
    assert ma.get_detail_actions() == []


def test_delete_selected_stays_off_the_detail_page_even_when_named():
    ma = make(actions=[Action("a", _noop)], detail_actions=["a", DELETE_SELECTED_NAME])
    assert names(ma.get_detail_actions()) == ["a"]


def test_a_replacement_delete_selected_is_also_kept_off_the_detail_page():
    ma = make(actions=[Action(DELETE_SELECTED_NAME, _noop)])
    assert DELETE_SELECTED_NAME not in names(ma.get_detail_actions())
    assert DELETE_SELECTED_NAME in names(ma.get_list_actions())


def test_unknown_detail_action_fails_at_registration():
    ma = make(actions=[Action("a", _noop)], detail_actions=["a", "nope"])
    with pytest.raises(ValueError, match="nope"):
        Admin(model_admins=[ma])
