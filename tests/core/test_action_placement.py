"""Where an action appears: the list page, the detail page, or both."""

import pytest

from polyadmin.core.action import DELETE_SELECTED_NAME, action
from polyadmin.core.admin import Admin
from tests.core.test_model_admin import InMemoryUserAdmin


def method(**options):
    """A decorated action method, for building a ModelAdmin with type()."""

    def handler(self, objects, principal):
        return None

    return action(**options)(handler)


def names(actions):
    return [a.name for a in actions]


def make(**attrs):
    return type("Users", (InMemoryUserAdmin,), attrs)()


def test_default_placement_follows_where():
    ma = make(
        both=method(),
        only_list=method(where="list"),
        only_detail=method(where="detail"),
    )
    assert names(ma.get_list_actions()) == ["both", "only_list", DELETE_SELECTED_NAME]
    assert names(ma.get_detail_actions()) == ["both", "only_detail"]


def test_delete_selected_never_reaches_the_detail_page():
    assert DELETE_SELECTED_NAME not in names(make().get_detail_actions())


def test_detail_actions_is_an_ordered_allowlist_that_overrides_where():
    ma = make(a=method(), b=method(where="list"), c=method(), detail_actions=["c", "b"])
    assert names(ma.get_detail_actions()) == ["c", "b"]
    # The list page is unaffected by detail_actions.
    assert names(ma.get_list_actions()) == ["a", "b", "c", DELETE_SELECTED_NAME]


def test_empty_detail_actions_means_none():
    assert make(a=method(), detail_actions=[]).get_detail_actions() == []


def test_delete_selected_stays_off_the_detail_page_even_when_named():
    ma = make(a=method(), detail_actions=["a", DELETE_SELECTED_NAME])
    assert names(ma.get_detail_actions()) == ["a"]


def test_an_overridden_delete_selected_is_also_kept_off_the_detail_page():
    ma = make(delete_selected=method())
    assert DELETE_SELECTED_NAME not in names(ma.get_detail_actions())
    assert DELETE_SELECTED_NAME in names(ma.get_list_actions())


def test_unknown_detail_action_fails_at_registration():
    ma = make(a=method(), detail_actions=["a", "nope"])
    with pytest.raises(ValueError, match="nope"):
        Admin(model_admins=[ma])
