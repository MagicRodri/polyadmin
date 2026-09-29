import asyncio

import pytest

from polyadmin.core.dashboard import WidgetContext
from polyadmin.core.widget import Column, DataTable, MetricGroup, Rows, Tile, next_offset


def ctx(**kwargs):
    return WidgetContext({}, **kwargs)


def test_metric_group_calls_its_tiles_with_the_context():
    seen = []

    async def tiles(c):
        seen.append(c.search)
        return [Tile("Doors", 12, icon="door", hint="all")]

    group = MetricGroup("Overview", get_tiles=tiles)
    assert group.lazy is True
    data = asyncio.run(group.get_data(ctx(search="s")))
    assert data == {"tiles": [Tile("Doors", 12, icon="door", hint="all")], "empty": False}
    assert seen == ["s"]


def test_metric_group_without_tiles_is_empty():
    assert asyncio.run(MetricGroup("O", get_tiles=lambda: []).get_data(ctx()))["empty"] is True


def test_column_rejects_unknown_format_and_alignment():
    with pytest.raises(ValueError):
        Column("a", "A", format="money")
    with pytest.raises(ValueError):
        Column("a", "A", align="center")


@pytest.mark.parametrize(
    ("rows", "offset", "limit", "expected"),
    [
        (Rows([{}] * 50, total=120), 0, 50, 50),
        (Rows([{}] * 20, total=120), 100, 50, None),
        (Rows([{}] * 50), 0, 50, 50),
        (Rows([{}] * 10), 0, 50, None),
        (Rows([]), 0, 50, None),
        (Rows([{}] * 50, total=50), 0, 50, None),
        (Rows([{}] * 5, total=5), 0, None, None),
    ],
)
def test_next_offset(rows, offset, limit, expected):
    assert next_offset(rows, offset, limit) == expected


def test_data_table_pages_with_the_context_and_formats_its_footer():
    calls = []

    async def rows(c):
        calls.append((c.offset, c.limit, c.search))
        return Rows([{"name": "a"}], total=3, totals={"name": "All"})

    table = DataTable(
        "Contracts",
        columns=[Column("name", "Name")],
        get_rows=rows,
        page_size=1,
        searchable=True,
        total_label="Total: {total}",
    )
    data = asyncio.run(table.get_data(ctx(offset=0, limit=1, search="x")))
    assert calls == [(0, 1, "x")]
    assert data["next_offset"] == 1
    assert data["footer"] == "Total: 3"
    assert data["empty"] is False
    assert data["rows"].totals == {"name": "All"}


def test_data_table_first_page_without_rows_or_totals_is_empty():
    table = DataTable("T", columns=[Column("a", "A")], get_rows=lambda c: Rows([], total=0))
    assert asyncio.run(table.get_data(ctx(limit=50)))["empty"] is True


def test_data_table_rejects_a_non_rows_result():
    table = DataTable("T", columns=[Column("a", "A")], get_rows=lambda c: [])
    with pytest.raises(TypeError):
        asyncio.run(table.get_data(ctx()))


def test_a_donut_with_a_context_aware_series_is_lazy_and_resolves():
    from polyadmin.core.widget import Donut, resolve_widget_data

    async def series(c):
        return [("Key", 3), ("Face", 1)]

    donut = Donut("Methods", get_series=series)
    assert donut.lazy is True
    data = asyncio.run(resolve_widget_data(donut, ctx()))
    assert [s["label"] for s in data["slices"]] == ["Key", "Face"] and data["total"] == 4
    assert Donut("Static", get_series=lambda: [("A", 1)]).lazy is False


def test_tabs_is_lazy_when_a_panel_is_and_resolves_every_panel():
    from polyadmin.core.widget import Donut, Metric, Tabs, resolve_widget_data

    async def series(c):
        return [("Key", 3)]

    tabs = Tabs("Breakdowns", panels=[("Methods", Donut("Methods", get_series=series)), ("Total", Metric("Total", value=7))])
    assert tabs.lazy is True
    data = asyncio.run(resolve_widget_data(tabs, ctx()))
    assert [p["label"] for p in data["panels"]] == ["Methods", "Total"]
    assert data["panels"][0]["data"]["total"] == 3 and data["panels"][1]["data"] == {"value": 7}
    legacy = Tabs("Legacy", panels=[("Total", Metric("Total", value=7))])
    assert legacy.lazy is False and legacy.get_data()["panels"][0]["data"] == {"value": 7}
