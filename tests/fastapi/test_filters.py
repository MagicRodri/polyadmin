"""The host-defined filter hook: a filter an application writes itself."""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.field import DateField
from polyadmin.core.filter import (
    EMPTY_FILTER_NOT_EMPTY,
    DateFilter,
    EmptyFilter,
    Filter,
)
from polyadmin.core.query import RANGE_FOR_FIELD, RANGE_FROM_FIELD, RANGE_TO_FIELD
from polyadmin.fastapi.router import create_router
from polyadmin.ui import ui
from tests.core.test_model_admin import InMemoryUserAdmin


class HostDomainFilter(Filter):
    """Written the way an application would write one: it subclasses the
    published base and implements the two methods, borrowing nothing from
    the framework's own filter types. Django calls this a
    SimpleListFilter -- lookups() plus queryset().
    """

    def choices_with_labels(self):
        return [("", "All"), ("example.com", "example.com"), ("other.test", "other.test")]

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects
        field = model_admin.get_field("email")
        return [obj for obj in objects if str(field.get_value(obj)).endswith("@" + raw_value)]


def _client(user_admin):
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_a_host_defined_filter_narrows_the_list_and_its_export():
    """The whole point of the hook is that a host filter is not a
    second-class citizen -- it rides in the same ListRequest as a
    built-in, so the export and delete_selected's "all N matching" agree
    with what the table shows."""
    user_admin = InMemoryUserAdmin()
    user_admin.filters = [HostDomainFilter("domain")]
    user_admin.create({"email": "keep@example.com"})
    user_admin.create({"email": "drop@other.test"})
    client = _client(user_admin)

    page = client.get("/admin/users", params={"filter[domain]": "example.com"}).text
    assert "keep@example.com" in page, "the host filter dropped a row it should have kept"
    assert "drop@other.test" not in page, "the host filter kept a row it should have dropped"
    assert "other.test" in page, "the host filter's own choices are not in the panel"

    csv = client.get("/admin/users/export/csv", params={"filter[domain]": "example.com"}).text
    assert "keep@example.com" in csv and "drop@other.test" not in csv, (
        f"the export ignored the host filter:\n{csv}"
    )


class RangeUserAdmin(InMemoryUserAdmin):
    """A user admin with a date field and a DateFilter on it. Declared as a
    subclass rather than assigned onto an instance: ModelAdmin builds its
    field map in __init__, so a later `fields` assignment never reaches it.
    """

    list_display = ["id", "email", "joined"]
    fields = [*InMemoryUserAdmin.fields, DateField("joined")]
    filters = [DateFilter("joined")]


def _range_admin():
    return RangeUserAdmin()


def test_the_date_filter_panel_offers_a_range_form():
    user_admin = _range_admin()
    user_admin.create({"email": "a@example.com"})
    page = _client(user_admin).get(
        "/admin/users", params={"search": "a", "sort": "-email"}
    ).text

    assert f'name="{RANGE_FROM_FIELD}"' in page, "no range form in the panel"
    # The form must carry the rest of the list, or applying a range
    # silently drops the reader's search and sort.
    for want in ('name="search" value="a"', 'name="sort" value="-email"'):
        assert want in page, f"the range form does not carry {want}"


def test_a_range_submission_narrows_the_list():
    user_admin = _range_admin()
    inside = user_admin.create({"email": "inside@example.com"})
    outside = user_admin.create({"email": "outside@example.com"})
    inside.joined = date(2026, 2, 1)
    outside.joined = date(2025, 2, 1)

    # Exactly what the form submits, including the blank end.
    page = _client(user_admin).get(
        "/admin/users",
        params={RANGE_FOR_FIELD: "joined", RANGE_FROM_FIELD: "2026-01-01", RANGE_TO_FIELD: ""},
    ).text
    assert "inside@example.com" in page, "the range dropped a row inside it"
    assert "outside@example.com" not in page, "the range kept a row outside it"


def test_the_panel_prefills_a_range_it_is_showing():
    page = _client(_range_admin()).get(
        "/admin/users", params={"filter[joined]": "2026-01-01:2026-03-01"}
    ).text
    assert 'value="2026-01-01"' in page and 'value="2026-03-01"' in page, (
        "the panel did not prefill the range it is filtering by"
    )


def test_a_set_range_counts_as_an_active_filter():
    """The badge says how much the panel is hiding without being opened,
    and Clear-all has to drop a range like any other filter -- a range
    that survived "Clear all" would be an invisible constraint."""
    user_admin = _range_admin()
    user_admin.create({"email": "a@example.com"})
    page = _client(user_admin).get(
        "/admin/users", params={"filter[joined]": "2026-01-01:2026-03-01"}
    ).text

    assert ui("filter-panel", "count") in page, "a set range is not counted in the Filters badge"
    assert "Clear all" in page, "no Clear-all control while a range is set"


def test_the_new_filters_narrow_the_export_too():
    """A filter that narrows the table but not the export turns "all N
    matching" into a lie, which is the one thing the single-ListRequest
    design exists to prevent."""

    class ExportAdmin(RangeUserAdmin):
        filters = [EmptyFilter("email"), DateFilter("joined")]

    user_admin = ExportAdmin()
    blank = user_admin.create({"email": ""})
    filled = user_admin.create({"email": "filled@example.com"})
    blank.joined = date(2026, 2, 1)
    filled.joined = date(2026, 2, 1)
    client = _client(user_admin)

    for name, params, want, not_want in (
        ("empty", {"filter[email]": EMPTY_FILTER_NOT_EMPTY}, "filled@example.com", None),
        ("range", {"filter[joined]": "2026-01-01:2026-03-01"}, "filled@example.com", None),
        ("range excludes", {"filter[joined]": "2025-01-01:2025-03-01"}, None, "filled@example.com"),
    ):
        csv = client.get("/admin/users/export/csv", params=params).text
        if want is not None:
            assert want in csv, f"{name}: export dropped {want!r}\n{csv}"
        if not_want is not None:
            assert not_want not in csv, f"{name}: export kept {not_want!r}\n{csv}"
