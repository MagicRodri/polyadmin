from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from polyadmin.core.field import DateField, DateTimeField, DecimalField, ImageField, IntegerField
from polyadmin.templating import Renderer, decimal_display
from polyadmin.ui import ui


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


@pytest.mark.parametrize(
    ("value", "want"),
    [
        (100.0, "100"),  # no trailing ".0" -- str(100.0) would render "100.0"
        (1234.5, "1234.5"),
        (0.1, "0.1"),
        (1e21, "1000000000000000000000"),  # not "1e+21"
        (1e-7, "0.0000001"),  # not "1e-07"
        (-2.50, "-2.5"),
    ],
)
def test_float_decimals_render_as_shortest_fixed_point(value, want):
    # Matches Go's decimalText (strconv.FormatFloat(f, 'f', -1, 64)):
    # the shortest digit string that round-trips to the same float, in
    # fixed-point, with no forced trailing zero -- Field.parse_form_value
    # (core/field.py) hands back exactly this type for a "decimal" field,
    # so any host's float must render identically in both languages.
    assert decimal_display(value) == want


def test_a_whole_number_float_balance_renders_without_a_decimal_point():
    got = render_value(DecimalField("x"), 100.0)
    assert got == '<span data-format="decimal" data-value="100">100</span>'


def test_a_decimal_keeps_its_own_precision_unlike_a_float():
    # decimal_display never trims a Decimal's own trailing zeros -- only a
    # float (which carries no such intent) gets the shortest-form
    # treatment above.
    assert decimal_display(Decimal("12.50")) == "12.50"


def test_image_field_renders_a_thumbnail_linked_to_the_full_image():
    # list, detail, and inline rows all go through render_field_value, so
    # a thumbnail here covers all three at once -- see field.html.
    url = "https://example.com/pic.jpg"
    got = render_value(ImageField("x"), url)

    thumb = ui("image", "thumb")
    assert f'<img src="{url}"' in got and thumb in got, f"no themed thumbnail in {got!r}"
    # Clicking through to the original is the only way to see it full
    # size -- there is no lightbox.
    assert f'<a href="{url}" target="_blank"' in got, f"the thumbnail does not link to the full image: {got!r}"


def test_image_field_thumbnail_falls_back_on_load_error():
    # A dead URL would otherwise show the browser's bare broken-image
    # icon, which is what the rest of the admin avoids.
    got = render_value(ImageField("x"), "https://example.com/dead.jpg")

    fallback = ui("image", "fallback")
    assert fallback in got, f"no fallback element for a failed load: {got!r}"
    assert 'style="display:none"' in got, f"the fallback is not hidden until the image actually fails: {got!r}"
    assert "onerror=" in got, f"nothing swaps the fallback in when the image fails: {got!r}"


def test_image_field_fallback_stays_hidden_despite_inline_flex():
    # The fallback's own class sets display:inline-flex for once it's
    # shown, but the browser's default `[hidden] { display: none }` is a
    # lowest-priority UA rule -- any author stylesheet, including a
    # Tailwind utility class on the same element, wins over it regardless
    # of order, so a plain `hidden` attribute is not actually hidden
    # here. Confirmed live with Playwright against the real Tailwind CDN
    # build: the fallback rendered a real 32x32 box even though `hidden`
    # was present. An inline style, not the attribute, has to be the one
    # holding it closed.
    got = render_value(ImageField("x"), "https://example.com/pic.jpg")
    assert " hidden>" not in got and " hidden " not in got, (
        f"the fallback relies on the hidden attribute, which a display utility class on the same element overrides: {got!r}"
    )


def render_input(field, value):
    env = Renderer().env
    template = env.from_string(
        '{% from "admin/components/ui/field.html" import render_form_input %}{{ render_form_input(field, value, []) }}'
    )
    return template.render(field=field, value=value, base_path="/admin")


@pytest.mark.parametrize(
    ("field", "value", "want"),
    [
        # A date or datetime-local input discards anything but its own ISO
        # form: str() of an aware datetime carries an offset (and a space),
        # which datetime-local rejects.
        (DateField("x"), date(2019, 3, 1), 'value="2019-03-01"'),
        (DateField("x"), datetime(2019, 3, 1, 9, 5, tzinfo=timezone.utc), 'value="2019-03-01"'),
        (DateTimeField("x"), datetime(2019, 3, 1, 9, 5, 30, tzinfo=timezone(timedelta(hours=2))), 'value="2019-03-01T09:05"'),
        (DateTimeField("x"), datetime(2019, 3, 1, 9, 5, 30), 'value="2019-03-01T09:05"'),  # noqa: DTZ001 -- naive on purpose
        (DateTimeField("x"), datetime(99, 3, 1, 10, 30), 'value="0099-03-01T10:30"'),  # noqa: DTZ001 -- naive on purpose
        (DateField("x"), None, 'value=""'),
        (DateField("x"), "2019-03-01", 'value="2019-03-01"'),
    ],
)
def test_date_inputs_are_filled_with_their_iso_form(field, value, want):
    assert want in render_input(field, value)


def test_image_field_form_input_is_a_url_input():
    # No upload handling yet -- the form just takes the image's URL, with
    # the browser's own URL validation.
    assert 'type="url"' in render_input(ImageField("x"), "")
