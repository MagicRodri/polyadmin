from polyadmin.core.widget import Activity, Chart, Metric, Progress, Stat, Table, Tabs, Timeline


def test_metric_static_value():
    assert Metric("Users", value=42).get_data() == {"value": 42}


def test_metric_computed_value():
    widget = Metric("Users", get_value=lambda: 7)
    assert widget.get_data() == {"value": 7}


def test_progress_percent():
    widget = Progress("Tasks", value=25, target=100)
    assert widget.get_data() == {"value": 25, "target": 100, "percent": 25}


def test_progress_caps_at_100_percent():
    widget = Progress("Tasks", value=150, target=100)
    assert widget.get_data()["percent"] == 100


def test_progress_zero_target_is_zero_percent():
    widget = Progress("Tasks", value=5, target=0)
    assert widget.get_data()["percent"] == 0


def test_progress_computed():
    widget = Progress("Tasks", get_data=lambda: (3, 4))
    assert widget.get_data() == {"value": 3, "target": 4, "percent": 75}


def test_table_static_rows():
    widget = Table("Recent", columns=["id", "email"], rows=[{"id": 1, "email": "a@example.com"}])
    assert widget.get_data() == {
        "columns": ["id", "email"],
        "rows": [{"id": 1, "email": "a@example.com"}],
    }


def test_table_computed_rows():
    widget = Table("Recent", columns=["id"], get_rows=lambda: [{"id": 1}])
    assert widget.get_data()["rows"] == [{"id": 1}]


def test_chart_computes_percentages_relative_to_max():
    widget = Chart("Signups", series=[("Mon", 10), ("Tue", 20), ("Wed", 5)])
    assert widget.get_data()["series"] == [("Mon", 10, 50), ("Tue", 20, 100), ("Wed", 5, 25)]


def test_chart_empty_series():
    widget = Chart("Signups", series=[])
    assert widget.get_data()["series"] == []


def test_activity_entries():
    widget = Activity("Feed", entries=["User created", "User deleted"])
    assert widget.get_data() == {"entries": ["User created", "User deleted"]}


def test_stat_reports_direction_and_unsigned_delta():
    assert Stat("Sales", value="$45,385", delta=12.5).get_data() == {
        "value": "$45,385",
        "delta": 12.5,
        "direction": "up",
    }
    assert Stat("Sales", value=1, delta=-4.26).get_data() == {
        "value": 1,
        "delta": 4.3,
        "direction": "down",
    }
    assert Stat("Sales", value=1).get_data()["direction"] == "flat"


def test_stat_computed():
    widget = Stat("Sales", get_stat=lambda: ("$10", 3.0))
    assert widget.get_data() == {"value": "$10", "delta": 3.0, "direction": "up"}


def test_timeline_entries_become_named_fields():
    widget = Timeline("Latest activity", entries=[("2h ago", "User created", "a@example.com")])
    assert widget.get_data() == {
        "entries": [{"time": "2h ago", "title": "User created", "description": "a@example.com"}]
    }


def test_timeline_computed():
    widget = Timeline("Latest activity", get_entries=lambda: [("now", "Deployed", "")])
    assert widget.get_data()["entries"][0]["title"] == "Deployed"


def test_tabs_hands_panel_widgets_to_the_template():
    products = Table("Top products", columns=["name"], rows=[{"name": "Widget Pro"}])
    widget = Tabs("Statistics", panels=[("Products", products)])
    panels = widget.get_data()["panels"]
    assert panels[0]["label"] == "Products"
    # The widget itself is passed through, so tabs.html can render it
    # via its own `template` and `get_data()`.
    assert panels[0]["widget"] is products
