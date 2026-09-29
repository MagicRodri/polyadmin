import pytest

from polyadmin import ActionFormError, Download
from polyadmin.core.action import action, collect_actions
from polyadmin.core.field import StringField
from polyadmin.core.model_admin import ModelAdmin


class Thing:
    pass


class FormAdmin(ModelAdmin):
    model = Thing
    slug = "things"

    @action(form=[StringField("reason", required=True)], submit_label="Go")
    def with_form(self, objects, principal, data):
        return None

    @action
    def plain(self, objects, principal):
        return None


def test_collect_actions_carries_form_and_submit_label():
    actions = {a.name: a for a in collect_actions(FormAdmin())}
    assert [f.name for f in actions["with_form"].form] == ["reason"]
    assert actions["with_form"].submit_label == "Go"
    assert actions["plain"].form is None


def test_callable_form_is_resolved_against_the_model_admin():
    class Dynamic(ModelAdmin):
        model = Thing
        slug = "dynamic"
        marker = "picked"

        @action(form=lambda ma: [StringField(ma.marker)])
        def run(self, objects, principal, data):
            return None

    resolved = {a.name: a for a in collect_actions(Dynamic())}["run"]
    assert [f.name for f in resolved.form] == ["picked"]


def test_form_and_confirm_are_mutually_exclusive():
    with pytest.raises(ValueError, match="confirm"):
        action(form=[StringField("x")], confirm="Sure?")


def test_form_action_must_accept_data():
    with pytest.raises(TypeError, match="data"):

        @action(form=[StringField("x")])
        def missing_data(self, objects, principal):
            return None


def test_plain_action_must_not_expect_data():
    with pytest.raises(TypeError, match="form"):

        @action
        def wants_data(self, objects, principal, data):
            return None


def test_varargs_handlers_skip_the_arity_check():
    @action(form=[StringField("x")])
    def flexible(self, *args):
        return None


def test_download_requires_exactly_one_body():
    with pytest.raises(ValueError):
        Download("a.csv")
    with pytest.raises(ValueError):
        Download("a.csv", content=b"x", stream=iter([b"x"]))
    assert Download("a.csv", content=b"x").content == b"x"


def test_action_form_error_keeps_errors():
    exc = ActionFormError({"reason": ["Too short."]})
    assert exc.errors == {"reason": ["Too short."]}


def test_plain_action_may_take_an_optional_fourth_parameter():
    @action
    def tag(self, objects, principal, note=None):
        return None


def test_form_action_may_take_optional_extra_parameters():
    @action(form=[StringField("x")])
    def run(self, objects, principal, data, extra=None):
        return None
