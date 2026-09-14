from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from polyadmin.core.field import DateField, DateTimeField, DecimalField, IntegerField
from polyadmin.templating import Renderer


def render_value(field, value):
    env = Renderer().env
    template = env.from_string(
        '{% from "admin/components/field.html" import render_field_value %}{{ render_field_value(field, value) }}'
    )
    return template.render(field=field, value=value).strip()


def test_date_renders_as_a_time_element():
    assert render_value(DateField("x"), date(2026, 9, 14)) == '<time datetime="2026-09-14" data-format="date">2026-09-14</time>'
    assert 'datetime="2026-09-14"' in render_value(DateField("x"), "2026-09-14")


def test_datetime_keeps_its_offset_and_naive_stays_naive():
    aware = datetime(2026, 9, 14, 10, 30, tzinfo=timezone(timedelta(hours=2)))
    assert render_value(DateTimeField("x"), aware) == (
        '<time datetime="2026-09-14T10:30:00+02:00" data-format="datetime">2026-09-14T10:30:00+02:00</time>'
    )
    assert 'datetime="2026-09-14T10:30:00"' in render_value(DateTimeField("x"), datetime(2026, 9, 14, 10, 30))  # noqa: DTZ001 -- naive on purpose


def test_decimal_carries_its_raw_value():
    assert render_value(DecimalField("x"), Decimal("1234.5")) == '<span data-format="decimal" data-value="1234.5">1234.5</span>'


def test_integers_are_not_formatted():
    assert render_value(IntegerField("x"), 1234) == "1234"


def test_unparseable_date_falls_back_to_text():
    assert render_value(DateField("x"), "someday") == "someday"


def test_decimal_never_renders_in_scientific_notation():
    # A Decimal built from scientific-notation input (however it got that
    # way) must still render fixed-point: the browser-side formatter
    # counts data-value's fraction digits by splitting on ".", which a
    # "1E+21" would throw off.
    got = render_value(DecimalField("x"), Decimal("1E+21"))
    assert got == '<span data-format="decimal" data-value="1000000000000000000000">1000000000000000000000</span>'
    assert "E+" not in got and "e+" not in got
