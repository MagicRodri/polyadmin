from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.dashboard import Dashboard
from polyadmin.core.widget import Activity, Chart, Metric, Progress, Stat, Table, Tabs, Timeline
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


def make_client(dashboard=None):
    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin], dashboard=dashboard)
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_no_dashboard_configured_redirects_to_first_resource():
    client, _ = make_client(dashboard=None)
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/admin/users"


def test_dashboard_renders_at_admin_root():
    client, user_admin = make_client(Dashboard(title="Overview", widgets=[Metric("Users", get_value=lambda: len(user_admin.get_queryset()))]))
    user_admin.create({"email": "a@example.com"})
    user_admin.create({"email": "b@example.com"})

    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 200
    assert "Overview" in response.text
    assert ">2<" in response.text


def test_dashboard_renders_all_widget_types():
    dashboard = Dashboard(
        widgets=[
            Metric("Users", value=10),
            Progress("Onboarding", value=3, target=10),
            Table("Recent", columns=["email"], rows=[{"email": "a@example.com"}]),
            Chart("Signups", series=[("Mon", 5), ("Tue", 10)]),
            Activity("Feed", entries=["User created"]),
        ]
    )
    client, _ = make_client(dashboard)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Onboarding" in response.text
    assert "a@example.com" in response.text
    assert "Signups" in response.text
    assert "User created" in response.text


def test_dashboard_omits_widget_denied_by_authorizer():
    class DenyRevenueAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "analytics.revenue.view"

    dashboard = Dashboard(
        widgets=[
            Metric("Users", value=1),
            Metric("Revenue", value=1, permission="analytics.revenue.view"),
        ]
    )
    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin], dashboard=dashboard, authorizer=DenyRevenueAuthorizer())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    response = client.get("/admin")
    assert response.status_code == 200
    assert "Users" in response.text
    assert "Revenue" not in response.text


def test_dashboard_view_requires_dashboard_permission():
    class DenyDashboardAuthorizer:
        def can(self, principal, permission, resource=None):
            return permission != "dashboard.view"

    admin = Admin(
        model_admins=[InMemoryUserAdmin()],
        dashboard=Dashboard(widgets=[Metric("Users", value=1)]),
        authorizer=DenyDashboardAuthorizer(),
    )
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    client = TestClient(app)

    assert client.get("/admin").status_code == 403


# The tabs widget is the only one that renders other widgets inside
# itself, so cover the round trip: each panel's child widget must
# actually reach the page.
def test_dashboard_renders_nested_tabs_panels():
    dashboard = Dashboard(
        widgets=[
            Tabs(
                "Statistics",
                panels=[
                    ("Top products", Table("Products", columns=["name"], rows=[{"name": "Widget Pro"}])),
                    ("Top customers", Activity("Customers", entries=["a@example.com"])),
                ],
            )
        ]
    )
    client, _ = make_client(dashboard)
    response = client.get("/admin")
    assert response.status_code == 200
    for expected in ("Top products", "Top customers", "Widget Pro", "a@example.com", 'role="tablist"'):
        assert expected in response.text


def test_dashboard_tabs_leaves_outer_widget_data_intact():
    # Each panel rebinds `widget_data` inside a `{% with %}` scope; if
    # that leaked, the second panel -- and the widget after the Tabs --
    # would render against the first panel's data.
    dashboard = Dashboard(
        widgets=[
            Tabs(
                "Statistics",
                panels=[
                    ("First", Activity("A", entries=["first-entry"])),
                    ("Second", Activity("B", entries=["second-entry"])),
                ],
            ),
            Metric("Users", value=99),
        ]
    )
    client, _ = make_client(dashboard)
    response = client.get("/admin")
    assert "first-entry" in response.text
    assert "second-entry" in response.text
    assert ">99<" in response.text


def test_dashboard_stat_renders_delta_direction():
    client, _ = make_client(Dashboard(widgets=[Stat("Sales", value="$45,385", delta=-12.5)]))
    response = client.get("/admin")
    assert "$45,385" in response.text
    assert "12.5%" in response.text
    # A negative delta reads in the destructive token (not a literal
    # red), so it follows whichever theme is active -- see polyadmin/ui.py.
    assert "text-destructive" in response.text


def test_dashboard_renders_timeline():
    dashboard = Dashboard(
        widgets=[Timeline("Latest activity", entries=[("2h ago", "User created", "a@example.com")])]
    )
    client, _ = make_client(dashboard)
    response = client.get("/admin")
    assert "2h ago" in response.text
    assert "User created" in response.text
