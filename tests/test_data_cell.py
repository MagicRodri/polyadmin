from datetime import datetime, timezone

from polyadmin.core.widget import Column
from polyadmin.templating import data_cell
from polyadmin.ui import ui


def test_empty_cell_shows_its_badge_or_a_dash():
    assert data_cell(Column("a", "A", empty="never"), None) == f'<span class="{ui("badge", "secondary")}">never</span>'
    assert data_cell(Column("a", "A"), "") == f'<span class="{ui("text", "placeholder")}">—</span>'


def test_number_and_percent_defer_to_the_browser_formatter():
    assert data_cell(Column("a", "A", format="number"), 1234) == '<span data-format="decimal" data-value="1234">1234</span>'
    assert data_cell(Column("a", "A", format="percent"), 87.25) == '<span data-format="decimal" data-value="87.2">87.2</span>%'


def test_share_hides_the_percentage_for_zero():
    column = Column("a", "A", format="share")
    assert data_cell(column, {"count": 0, "percentage": 0}) == '<span data-format="decimal" data-value="0">0</span>'
    assert data_cell(column, {"count": 12, "percentage": 34.5}) == (
        '<span data-format="decimal" data-value="12">12</span>'
        f' <span class="{ui("text", "muted")}">(<span data-format="decimal" data-value="34.5">34.5</span>%)</span>'
    )


def test_datetime_uses_the_time_element():
    value = datetime(2026, 9, 1, 10, 30, tzinfo=timezone.utc)
    assert data_cell(Column("a", "A", format="datetime"), value) == (
        '<time datetime="2026-09-01T10:30:00+00:00" data-format="datetime">2026-09-01T10:30:00+00:00</time>'
    )
    assert data_cell(Column("a", "A", format="datetime"), "2026-09-01T10:30:00Z") == (
        '<time datetime="2026-09-01T10:30:00Z" data-format="datetime">2026-09-01T10:30:00Z</time>'
    )


def test_text_is_escaped():
    assert data_cell(Column("a", "A"), "<b>") == "&lt;b&gt;"


TONES = ((80, "success"), (50, "warning"), (0, "danger"))


def test_tones_wrap_the_value_in_a_coloured_badge():
    column = Column("rate", "Rate", format="percent", tones=TONES)
    assert data_cell(column, 87.5) == (
        f'<span class="{ui("badge", "success")}"><span data-format="decimal" data-value="87.5">87.5</span>%</span>'
    )
    assert data_cell(column, 50) == (
        f'<span class="{ui("badge", "warning")}"><span data-format="decimal" data-value="50.0">50.0</span>%</span>'
    )
    assert data_cell(column, 12) == (
        f'<span class="{ui("badge", "danger")}"><span data-format="decimal" data-value="12.0">12.0</span>%</span>'
    )


def test_a_value_below_every_tone_is_left_plain():
    column = Column("n", "N", format="number", tones=((10, "success"),))
    assert data_cell(column, 3) == '<span data-format="decimal" data-value="3">3</span>'


def test_tones_must_name_a_known_colour():
    import pytest

    with pytest.raises(ValueError, match="tone"):
        Column("n", "N", tones=((10, "purple"),))
