import logging
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.dashboard import Dashboard, DateRangeFilter, SelectFilter
from polyadmin.core.widget import Column, DataTable, Metric, MetricGroup, Rows, Tile, WidgetUnavailable
from polyadmin.contrib.fastapi.router import create_router

TODAY = date(2026, 9, 29)
calls = []


async def tiles(ctx):
    return [Tile("Doors", 12, icon="door", hint="all doors")]


async def rows(ctx):
    calls.append((ctx.filters["store"], ctx.search, ctx.offset, ctx.limit))
    start = ctx.offset
    items = [{"name": f"row {i}", "count": {"count": i, "percentage": 10.0}} for i in range(start, min(start + ctx.limit, 5))]
    return Rows(items, total=5, totals={"name": "All"} if ctx.offset == 0 else None)


def broken(ctx):
    raise RuntimeError("boom")


def down(ctx):
    raise WidgetUnavailable("Analytics is down.")


class Down(MetricGroup):
    pass


def make_dashboard(**kwargs):
    return Dashboard(
        title="Stats",
        filters=[
            DateRangeFilter("period", label="Period", today=lambda: TODAY),
            SelectFilter("store", label="Store", empty_label="All stores", choices=[("7", "Downtown")]),
        ],
        widgets=[
            Metric("Legacy", value=41),
            MetricGroup("Overview", key="overview", depends_on=[], get_tiles=tiles),
            DataTable(
                "Stores",
                key="stores",
                columns=[Column("name", "Name", strong=True), Column("count", "Count", align="end", format="share")],
                get_rows=rows,
                page_size=2,
                searchable=True,
                total_label="Total: {total}",
                depends_on=["store"],
                description=lambda c: f"since {c.filters['period'].start}",
            ),
            MetricGroup("Broken", key="broken", get_tiles=broken),
            MetricGroup("Down", key="down", get_tiles=down),
            MetricGroup("Empty", key="empty", get_tiles=lambda: [], empty_text="Nothing here"),
            MetricGroup("Secret", key="secret", get_tiles=tiles, permission="secret.view"),
        ],
        **kwargs,
    )


def make_client(**admin_kwargs):
    calls.clear()
    app = FastAPI()
    admin = Admin(dashboard=make_dashboard(), **admin_kwargs)
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_page_renders_filters_from_the_query_and_placeholders_for_lazy_widgets():
    page = make_client().get("/admin?period_from=2026-01-01&period_to=2026-01-31&store=7").text
    assert 'id="dashboard-filters"' in page
    assert 'name="period_from"' in page and 'value="2026-01-01"' in page
    assert 'data-dashboard-filter="store"' in page and "Downtown" in page
    assert ">41<" in page
    assert 'id="widget-body-overview"' in page
    assert page.count('data-widget-state="loading"') == 6
    assert 'hx-get="/admin/_widgets/stores"' in page
    assert "since 2026-01-01" in page
    assert calls == []


def test_triggers_follow_depends_on():
    page = make_client().get("/admin").text
    overview = page.split('id="widget-body-overview"')[1].split(">")[0]
    stores = page.split('id="widget-body-stores"')[1].split(">")[0]
    broken_card = page.split('id="widget-body-broken"')[1].split(">")[0]
    assert 'hx-trigger="load"' in overview
    assert 'hx-trigger="load, dashboard-filter-store from:body"' in stores
    assert "dashboard-filter-period from:body, dashboard-filter-store from:body" in broken_card


def test_fragment_renders_tiles():
    body = make_client().get("/admin/_widgets/overview").text
    assert "data-tile" in body and "all doors" in body and 'data-value="12"' in body


def test_fragment_first_page_has_totals_rows_footer_and_next_page():
    body = make_client().get("/admin/_widgets/stores?store=7&search=ac").text
    assert calls == [("7", "ac", 0, 2)]
    assert "data-totals" in body and body.count("data-row") == 2
    assert "data-table-footer" in body and "Total: 5" in body
    assert 'hx-get="/admin/_widgets/stores?' in body and "offset=2" in body and "search=ac" in body and "store=7" in body


def test_fragment_later_page_returns_only_rows():
    body = make_client().get("/admin/_widgets/stores?offset=4").text
    assert "<table" not in body and "data-totals" not in body
    assert body.count("data-row") == 1
    assert "data-next-page" not in body


def test_fragment_with_garbage_offset_starts_at_zero():
    make_client().get("/admin/_widgets/stores?offset=abc")
    assert calls[0][2] == 0


def test_unavailable_and_generic_errors_render_the_unavailable_state(caplog):
    client = make_client()
    down_body = client.get("/admin/_widgets/down")
    assert down_body.status_code == 200
    assert 'data-widget-state="unavailable"' in down_body.text and "Analytics is down." in down_body.text
    with caplog.at_level(logging.ERROR, logger="polyadmin"):
        broken_body = client.get("/admin/_widgets/broken")
    assert broken_body.status_code == 200
    assert 'data-widget-state="unavailable"' in broken_body.text and "boom" not in broken_body.text
    assert any("broken" in r.getMessage() for r in caplog.records)


def test_empty_state_uses_the_widgets_text():
    assert "Nothing here" in make_client().get("/admin/_widgets/empty").text


def test_hidden_and_unknown_widgets_are_404():
    class DenySecret:
        def can(self, principal, permission, resource=None):
            return permission != "secret.view"

    client = make_client(authorizer=DenySecret())
    assert 'id="widget-secret"' not in client.get("/admin").text
    assert client.get("/admin/_widgets/secret").status_code == 404
    assert client.get("/admin/_widgets/nope").status_code == 404


def test_fragments_require_dashboard_view():
    class DenyDashboard:
        def can(self, principal, permission, resource=None):
            return permission != "dashboard.view"

    assert make_client(authorizer=DenyDashboard()).get("/admin/_widgets/overview").status_code in (401, 403)


def test_a_failing_choices_function_or_description_does_not_break_the_page(caplog):
    def choices():
        raise RuntimeError("analytics down")

    def description(ctx):
        raise RuntimeError("bad description")

    dashboard = Dashboard(
        filters=[SelectFilter("store", get_choices=choices)],
        widgets=[MetricGroup("Overview", key="overview", get_tiles=tiles, description=description)],
    )
    app = FastAPI()
    app.include_router(create_router(Admin(dashboard=dashboard), base_path="/admin"), prefix="/admin")
    with caplog.at_level(logging.ERROR, logger="polyadmin"):
        response = TestClient(app).get("/admin")
    assert response.status_code == 200
    assert 'data-dashboard-filter="store"' in response.text
    assert 'id="widget-overview"' in response.text
    assert any("store" in r.getMessage() for r in caplog.records)


def test_a_fragment_refreshes_its_cards_description():
    client = make_client()
    assert 'id="widget-description-stores"' in client.get("/admin").text
    body = client.get("/admin/_widgets/stores?period_from=2026-01-01&period_to=2026-01-31").text
    assert 'id="widget-description-stores"' in body and 'hx-swap-oob="true"' in body
    assert "since 2026-01-01" in body
    rows_only = client.get("/admin/_widgets/stores?offset=2").text
    assert "hx-swap-oob" not in rows_only


def test_a_top_widget_renders_above_the_filters_without_a_header():
    dashboard = Dashboard(
        filters=[SelectFilter("store", choices=[("7", "Downtown")])],
        widgets=[
            MetricGroup("Hidden title", key="overview", placement="top", depends_on=[], get_tiles=tiles),
            MetricGroup("Grid card", key="grid", get_tiles=tiles),
        ],
    )
    app = FastAPI()
    app.include_router(create_router(Admin(dashboard=dashboard), base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin").text
    assert page.index('id="widget-overview"') < page.index('id="dashboard-filters"') < page.index('id="widget-grid"')
    top_card = page.split('id="widget-overview"')[1].split('id="dashboard-filters"')[0]
    assert "Hidden title" not in top_card and "<h2" not in top_card
    assert 'id="widget-body-overview"' in top_card
    assert TestClient(app).get("/admin/_widgets/overview").status_code == 200


def test_placement_must_be_grid_or_top():
    import pytest

    with pytest.raises(ValueError, match="placement"):
        MetricGroup("X", get_tiles=tiles, placement="side")


def test_a_lazy_tabs_of_donuts_renders_through_its_fragment():
    from polyadmin.core.widget import Donut, Tabs

    async def methods(ctx):
        return [("Key", 3), ("Face", 1)]

    dashboard = Dashboard(widgets=[Tabs("Breakdowns", key="breakdowns", panels=[("Methods", Donut("Methods", get_series=methods))])])
    app = FastAPI()
    app.include_router(create_router(Admin(dashboard=dashboard), base_path="/admin"), prefix="/admin")
    client = TestClient(app)
    assert 'data-widget-state="loading"' in client.get("/admin").text.split('id="widget-breakdowns"')[1]
    body = client.get("/admin/_widgets/breakdowns").text
    assert 'role="tab"' in body and "Methods" in body and "Key" in body and "Face" in body


def test_a_searchable_select_filter_renders_a_search_box():
    dashboard = Dashboard(
        filters=[
            SelectFilter("store", choices=[("7", "Downtown")], searchable=True),
            SelectFilter("plain", choices=[("1", "One")]),
        ],
        widgets=[],
    )
    app = FastAPI()
    app.include_router(create_router(Admin(dashboard=dashboard), base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin").text
    store = page.split('data-dashboard-filter="store"')[1].split('data-dashboard-filter="plain"')[0]
    plain = page.split('data-dashboard-filter="plain"')[1].split("</form>")[0]
    assert 'x-ref="search"' in store and 'x-model="query"' in store and "No matches." in store
    assert 'x-ref="search"' not in plain
