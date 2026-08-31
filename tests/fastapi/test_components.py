"""Phase B/D component rendering -- mirrors go-polyadmin/fiber/components_test.go."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.field import DateField, EnumField, StringField
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.fastapi.router import create_router
from polyadmin.ui import ui
from tests.core.test_model_admin import InMemoryUserAdmin


# -- date picker (Phase D) ----------------------------------------------


class Task:
    def __init__(self, id, name, due_date="", priority="Medium"):
        self.id = id
        self.name = name
        self.due_date = due_date
        self.priority = priority


class TaskAdmin(ModelAdmin):
    model = Task

    list_display = ["id", "name", "due_date", "priority"]
    form_fields = ["name", "due_date", "priority"]
    fields = [
        StringField("name", required=True),
        DateField("due_date"),
        EnumField("priority", choices=["Low", "Medium", "High"]),
    ]

    def __init__(self):
        super().__init__()
        self._item = Task(id=1, name="Ship it", due_date="2026-03-14", priority="Medium")

    def get_queryset(self):
        return [self._item]

    def get_object(self, pk):
        return self._item


@pytest.fixture
def task_client():
    admin = Admin(model_admins=[TaskAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_date_field_renders_native_input_plus_calendar_popover(task_client):
    page = task_client.get("/admin/tasks/create").text

    # The native input is what actually posts, and is what keeps the
    # field working with Alpine absent -- it must survive the
    # enhancement, not be replaced by it.
    assert 'type="date" id="field-due_date" name="due_date"' in page
    # The Calendar port is layered on top.
    for fragment in (
        'x-data="adminCalendar()"',
        'x-ref="dateInput"',
        'aria-label="Open calendar"',
        'x-anchor.bottom-end.offset.6="$refs.trigger"',
        'x-for="day in days"',
    ):
        assert fragment in page, f"date picker missing {fragment}"


def test_date_field_prefills_existing_value(task_client):
    page = task_client.get("/admin/tasks/1/edit").text
    assert 'value="2026-03-14"' in page


def test_calendar_factory_is_defined_once_per_page(task_client):
    # The factory guards itself with `window.adminCalendar ||`, but the
    # <script> should still only be emitted once per page even when
    # several date fields are present -- it comes from base.html, not
    # from the field.
    page = task_client.get("/admin/tasks/create").text
    assert page.count("window.adminCalendar = window.adminCalendar ||") == 1


def test_date_field_still_wrapped_in_the_form_field_unit(task_client):
    # The picker replaces the *control*, not the label/description/error
    # wrapper the other field types share.
    page = task_client.get("/admin/tasks/create").text
    assert '<label for="field-due_date"' in page


def _filterable_page(query: str = "") -> str:
    """The list view of a ModelAdmin that declares a filter and has
    actions/export/create available, with `query` applied."""
    from polyadmin.core.action import Action
    from polyadmin.core.filter import BooleanFilter

    def _noop(model_admin, objects, principal):
        return ""

    filterable = InMemoryUserAdmin()
    filterable.filters = [BooleanFilter("is_active")]
    filterable.actions = [Action("touch", _noop)]
    filterable.create({"email": "jane@example.com"})
    admin = Admin(model_admins=[filterable])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app).get("/admin/users" + query).text


# Filtering is one drawer behind one toolbar trigger (Django admin's
# filter column, in Unfold's drawer form), not a dropdown per filter --
# so a ModelAdmin's filter count costs the toolbar nothing.
def test_filters_render_as_one_drawer_behind_one_trigger():
    page = _filterable_page()

    assert ui("toolbar", "filters") in page, "expected a toolbar filter cluster"
    assert 'aria-haspopup="dialog"' in page, "expected one Filters trigger opening a drawer"
    assert 'aria-label="Filters"' in page, "expected the drawer itself"
    assert "Is Active" in page, "expected the filter's label in the drawer"
    assert ui("sheet", "side-right") in page, "expected the drawer to come in from the right"


# The trigger carries a count so the drawer says how much it's hiding
# without being opened -- and only once something is applied.
def test_filter_trigger_counts_only_applied_filters():
    count = ui("filter-panel", "count")
    assert count not in _filterable_page(), "expected no count badge while nothing is filtered"
    applied = _filterable_page("?filter[is_active]=true")
    assert count in applied, "expected a count badge once a filter is applied"


# Reset clears search *and* every filter, so it lives with the things it
# clears -- in the drawer's footer -- which is also what keeps the
# stacked mobile toolbar to its five controls.
def test_reset_lives_in_the_drawer_and_only_when_something_is_applied():
    assert "Clear all" not in _filterable_page(), "expected no Reset while nothing is applied"
    applied = _filterable_page("?filter[is_active]=true")
    assert "Clear all" in applied, "expected Reset in the drawer once a filter is applied"


# Every toolbar control fills its own line while the toolbar is a single
# stacked column below sm. The ones wrapped in a <form> or a positioning
# <div> can't inherit that from the flex row, so each carries
# ui('toolbar', 'item') itself.
def test_toolbar_controls_fill_their_line_while_stacked():
    item = ui("toolbar", "item")
    page = _filterable_page()
    # search, the Filters trigger (wrapper + button), bulk actions
    # (form + button), Export, New.
    assert page.count(item) >= 6, (
        f"expected every stacked toolbar control to fill its line, found {page.count(item)}"
    )


# A stacked toolbar control is a full-width bar, so its label goes hard
# left and its icon hard right rather than sitting centred. Every control
# that has both carries the pair.
def test_stacked_toolbar_controls_put_the_label_left_and_the_icon_right():
    label = ui("toolbar", "item-label")
    icon_class = ui("toolbar", "item-icon")
    page = _filterable_page()

    # Filters, the action select, Export and New each get a label that
    # takes the slack.
    assert page.count(label) >= 4, (
        f"expected each stacked control's label to take the slack, found {page.count(label)}"
    )
    # Filters' and New's leading icons plus Export's icon+chevron move to
    # the trailing edge; the action select's chevron is already last and
    # needs no reorder.
    assert page.count(icon_class) >= 4, (
        f"expected leading icons to move to the trailing edge, found {page.count(icon_class)}"
    )


# A label is arbitrary application text, so it reaches Alpine as a data
# attribute the browser decodes -- never quoted into the x-data
# expression, where one stray quote closes the attribute and every select
# on the page fails to initialise. tojson did exactly that.
def test_select_label_is_a_data_attribute_not_a_js_string_literal(task_client):
    page = task_client.get("/admin/tasks/1/edit").text

    xdata = 'x-data="{ open: false, label: ' + "''" + ' }"'
    assert xdata in page, "expected the x-data to carry no interpolated label"
    assert 'x-init="label = $el.dataset.label"' in page, (
        "expected the label to be hydrated from the DOM"
    )
    assert 'data-label="Medium"' in page
    # The shape that broke: tojson's double quote closing the attribute.
    assert 'label: "' not in page


# -- booleans as icons ----------------------------------------------------




# A column of booleans is scannable as glyphs and not as two
# similar-length words, so list cells render a check or a cross. The word
# stays as an sr-only label, so nothing depends on the icon alone.


# Exports stringify through core/exporter.py, never through
# render_field_value, so a CSV still carries a readable value rather
# than an SVG.


# -- shadcn Select for plain choice fields -------------------------------


def test_enum_field_renders_shadcn_select_not_native_options(task_client):
    page = task_client.get("/admin/tasks/1/edit").text
    assert "<option" not in page, "expected no native <option> elements once enum uses ui/select"
    assert 'aria-haspopup="listbox"' in page
    assert 'name="priority"' in page
    assert "Medium" in page


def test_enum_field_select_lists_all_choices_as_options(task_client):
    page = task_client.get("/admin/tasks/create").text
    for want in ('data-value="Low"', 'data-value="Medium"', 'data-value="High"'):
        assert want in page, f"expected choice {want!r} as a listbox option"


# -- export dropdown (Phase B) ------------------------------------------


def test_list_renders_export_dropdown_rather_than_one_button_per_format():
    admin = Admin(model_admins=[InMemoryUserAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin/users").text

    assert 'aria-haspopup="menu"' in page, "expected the export DropdownMenu trigger"
    assert "/admin/users/export/csv" in page
    assert "/admin/users/export/xlsx" in page
    assert 'role="menuitem"' in page


# -- list-view reordering ------------------------------------------------


def test_list_shows_drag_handle_only_when_reorderable():
    plain = InMemoryUserAdmin()
    plain.create({"email": "jane@example.com"})
    admin = Admin(model_admins=[plain])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin/users").text
    assert "drag-handle" not in page, "expected no drag handle when enable_reordering is unset"

    reorderable = InMemoryUserAdmin()
    reorderable.create({"email": "jane@example.com"})
    reorderable.enable_reordering = True
    admin2 = Admin(model_admins=[reorderable])
    app2 = FastAPI()
    app2.include_router(create_router(admin2, base_path="/admin"), prefix="/admin")
    page2 = TestClient(app2).get("/admin/users").text
    assert "drag-handle" in page2, "expected a drag handle when enable_reordering is set"
    assert "Sortable.create" in page2, "expected the drag handle to be wired to SortableJS"


def test_list_row_actions_render_as_one_dropdown_menu():
    user_admin = InMemoryUserAdmin()
    user_admin.create({"email": "jane@example.com"})
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin/users").text

    assert 'aria-label="Open menu"' in page, "expected a single row-actions menu trigger"
    assert 'role="menuitem"' in page, "expected View/Edit/Delete as menu items"
    assert 'title="View"' not in page
    assert 'title="Edit"' not in page
    assert 'title="Delete"' not in page


# -- combobox (Phase D) -------------------------------------------------


def test_combobox_uses_token_classes():
    # The autocomplete relation field is the one genuinely Alpine-driven
    # form control; its panel/active-item classes must come from the
    # registry so it themes with everything else.
    assert "bg-popover" in ui("combobox", "content")
    # Applied/removed imperatively by the arrow-key handler, so it has to
    # stay a single class with no spaces.
    assert " " not in ui("combobox", "item-active")


def test_toast_viewport_sits_bottom_right_and_does_not_block_clicks():
    """shadcn's ToastViewport, pinned bottom-right. pointer-events-none
    matters: record pages now carry a sticky action bar in that same
    corner, and the viewport spans a strip of the screen even with no
    toasts in it -- without it, Save would be unclickable."""
    viewport = ui("toast", "list")
    assert "bottom-0" in viewport and "sm:right-0" in viewport
    assert "top-4" not in viewport, "toasts should no longer be top-anchored"
    assert "pointer-events-none" in viewport
    assert "pointer-events-auto" in ui("toast", "root"), (
        "each toast must re-enable pointer events for itself"
    )

    user_admin = InMemoryUserAdmin()
    user_admin.create({"email": "a@example.com"})
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin/users").text
    assert viewport in page
