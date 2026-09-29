import asyncio
from datetime import date

import pytest

from polyadmin.core.admin import Admin
from polyadmin.core.dashboard import (
    Dashboard,
    DashboardContext,
    DashboardExport,
    DateRange,
    DateRangeFilter,
    SelectFilter,
    WidgetContext,
)
from polyadmin.core.widget import Metric, Widget, WidgetUnavailable, resolve_widget_data, takes_context

TODAY = date(2026, 9, 29)


def period():
    return DateRangeFilter("period", default_days=30, today=lambda: TODAY)


def test_date_range_defaults_to_the_last_n_days():
    assert period().parse({}) == DateRange(date(2026, 8, 30), TODAY)


def test_date_range_parses_iso_dates():
    value = period().parse({"period_from": "2026-01-01", "period_to": "2026-01-31"})
    assert value == DateRange(date(2026, 1, 1), date(2026, 1, 31))


def test_date_range_falls_back_on_garbage_and_swaps_a_reversed_range():
    assert period().parse({"period_from": "nope", "period_to": "2026-09-29"}).start == date(2026, 8, 30)
    assert period().parse({"period_from": "2026-02-01", "period_to": "2026-01-01"}) == DateRange(
        date(2026, 1, 1), date(2026, 2, 1)
    )


def test_date_range_query_params_round_trip():
    f = period()
    value = DateRange(date(2026, 1, 1), date(2026, 1, 31))
    assert f.parse(f.query_params(value)) == value


def test_select_filter_parses_empty_as_none():
    f = SelectFilter("contract_id")
    assert f.parse({}) is None
    assert f.parse({"contract_id": ""}) is None
    assert f.parse({"contract_id": "42"}) == "42"
    assert f.query_params(None) == {}


def test_select_filter_resolves_sync_and_async_choices():
    async def load():
        return [(1, "One")]

    assert asyncio.run(SelectFilter("a", choices=[("x", "X")]).resolve_choices()) == [("x", "X")]
    assert asyncio.run(SelectFilter("a", get_choices=load).resolve_choices()) == [("1", "One")]


def test_widget_key_defaults_to_a_transliterated_slug():
    assert Metric("Статистика по проходам", value=1).key == "statistika-po-prokhodam"
    assert Metric("Users", value=1, key="u").key == "u"


def test_reloads_on_defaults_to_every_filter():
    assert Metric("A", value=1).reloads_on(["period", "c"]) == ["period", "c"]
    assert Metric("A", value=1, depends_on=[]).reloads_on(["period"]) == []
    assert Metric("A", value=1, depends_on=["c"]).reloads_on(["period", "c"]) == ["c"]


def test_description_may_be_a_callable_of_the_context():
    ctx = DashboardContext({"period": DateRange(date(2026, 1, 1), date(2026, 1, 2))})
    w = Metric("A", value=1, description=lambda c: f"from {c.filters['period'].start}")
    assert w.describe(ctx) == "from 2026-01-01"
    assert Metric("A", value=1, description="static").describe(ctx) == "static"


def test_legacy_widgets_are_not_lazy():
    assert Metric("A", value=1).lazy is False


def test_a_context_aware_or_async_widget_is_lazy():
    class Ctx(Widget):
        def get_data(self, ctx):
            return {"q": ctx.search}

    class Async(Widget):
        async def get_data(self):
            return {}

    assert Ctx("A").lazy is True
    assert Async("B").lazy is True
    ctx = WidgetContext({}, search="x")
    assert asyncio.run(resolve_widget_data(Ctx("A"), ctx)) == {"q": "x"}
    assert asyncio.run(resolve_widget_data(Metric("M", value=3), ctx)) == {"value": 3}


def test_takes_context_by_positional_parameter():
    assert takes_context(lambda ctx: 1) is True
    assert takes_context(lambda: 1) is False


def test_widget_context_parses_offset_and_search():
    d = Dashboard(filters=[period()], widgets=[])
    ctx = d.widget_context(Metric("A", value=1), {"offset": "50", "search": "acme"})
    assert (ctx.offset, ctx.search, ctx.limit) == (50, "acme", None)
    assert d.widget_context(Metric("A", value=1), {"offset": "-3"}).offset == 0
    assert d.widget_context(Metric("A", value=1), {"offset": "x"}).offset == 0


def test_dashboard_query_params_join_every_filter():
    d = Dashboard(filters=[period(), SelectFilter("c")])
    filters = d.parse_filters({"c": "7"})
    assert d.query_params(filters) == {"period_from": "2026-08-30", "period_to": "2026-09-29", "c": "7"}


def test_validation_rejects_duplicate_keys_exports_and_unknown_dependencies():
    with pytest.raises(ValueError, match="widget key"):
        Admin(dashboard=Dashboard(widgets=[Metric("A", value=1), Metric("A", value=2)]))
    with pytest.raises(ValueError, match="export name"):
        export = DashboardExport("x", "X", handler=lambda ctx: None)
        Admin(dashboard=Dashboard(exports=[export, export]))
    with pytest.raises(ValueError, match="unknown filter"):
        Admin(dashboard=Dashboard(widgets=[Metric("A", value=1, depends_on=["nope"])]))


def test_exports_are_filtered_by_permission():
    class DenyExport:
        def can(self, principal, permission, resource=None):
            return permission != "dashboard.export"

    d = Dashboard(exports=[DashboardExport("x", "X", handler=lambda ctx: None)])
    assert d.get_exports(None, None) == d.exports
    assert d.get_exports(None, DenyExport()) == []


def test_widget_unavailable_keeps_its_message():
    assert WidgetUnavailable("down").message == "down"
