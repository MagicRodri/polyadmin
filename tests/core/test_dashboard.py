from polyadmin.core.dashboard import Dashboard
from polyadmin.core.widget import Metric


class RecordingAuthorizer:
    def __init__(self, allowed_permissions):
        self.allowed_permissions = set(allowed_permissions)

    def can(self, principal, permission, resource=None):
        return permission in self.allowed_permissions


def test_widgets_without_permission_are_always_visible():
    dashboard = Dashboard(widgets=[Metric("Users", value=1)])
    assert dashboard.get_widgets() == dashboard.widgets


def test_widget_with_permission_shown_when_no_authorizer_configured():
    dashboard = Dashboard(widgets=[Metric("Revenue", value=1, permission="analytics.revenue.view")])
    assert dashboard.get_widgets(principal=None, authorizer=None) == dashboard.widgets


def test_widget_hidden_when_authorizer_denies():
    widget = Metric("Revenue", value=1, permission="analytics.revenue.view")
    dashboard = Dashboard(widgets=[widget])
    authorizer = RecordingAuthorizer(allowed_permissions=set())
    assert dashboard.get_widgets(principal=None, authorizer=authorizer) == []


def test_widget_shown_when_authorizer_grants():
    widget = Metric("Revenue", value=1, permission="analytics.revenue.view")
    dashboard = Dashboard(widgets=[widget])
    authorizer = RecordingAuthorizer(allowed_permissions={"analytics.revenue.view"})
    assert dashboard.get_widgets(principal=None, authorizer=authorizer) == [widget]


def test_mixed_widgets_only_omits_the_denied_one():
    always_visible = Metric("Users", value=1)
    gated = Metric("Revenue", value=1, permission="analytics.revenue.view")
    dashboard = Dashboard(widgets=[always_visible, gated])
    authorizer = RecordingAuthorizer(allowed_permissions=set())
    assert dashboard.get_widgets(principal=None, authorizer=authorizer) == [always_visible]
