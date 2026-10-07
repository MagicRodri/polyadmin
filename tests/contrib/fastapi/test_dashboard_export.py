from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin import Download
from polyadmin.core.admin import Admin
from polyadmin.core.dashboard import Dashboard, DashboardExport, DateRangeFilter, SelectFilter
from polyadmin.contrib.fastapi.router import create_router

seen = []


async def export_csv(ctx):
    seen.append((ctx.filters["period"].start, ctx.filters["store"]))
    return Download("stats.csv", "text/csv", content=b"a,b")


def make_client(authorizer=None, handler=export_csv):
    seen.clear()
    dashboard = Dashboard(
        filters=[DateRangeFilter("period", today=lambda: date(2026, 9, 29)), SelectFilter("store")],
        exports=[DashboardExport("csv", "Export CSV", handler=handler)],
    )
    app = FastAPI()
    app.include_router(create_router(Admin(dashboard=dashboard, authorizer=authorizer), base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_export_button_posts_the_filter_form():
    page = make_client().get("/admin").text
    assert 'formaction="/admin/_exports/csv"' in page and 'data-dashboard-export="csv"' in page


def test_export_passes_the_filters_and_returns_the_file():
    response = make_client().get("/admin/_exports/csv?period_from=2026-01-01&period_to=2026-01-31&store=7")
    assert response.status_code == 200
    assert response.content == b"a,b"
    assert response.headers["content-disposition"].startswith('attachment; filename="stats.csv"')
    assert seen == [(date(2026, 1, 1), "7")]


def test_export_needs_its_permission():
    class DenyExport:
        def can(self, principal, permission, resource=None):
            return permission != "dashboard.export"

    client = make_client(DenyExport())
    assert "data-dashboard-export" not in client.get("/admin").text
    assert client.get("/admin/_exports/csv").status_code == 403


def test_unknown_export_is_404():
    assert make_client().get("/admin/_exports/nope").status_code == 404


def test_a_handler_not_returning_a_download_is_a_server_error():
    client = TestClient(make_client(handler=lambda ctx: "nope").app, raise_server_exceptions=False)
    assert client.get("/admin/_exports/csv").status_code == 500
