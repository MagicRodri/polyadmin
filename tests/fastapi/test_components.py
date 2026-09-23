import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.field import DateField, EnumField, StringField
from polyadmin.core.model_admin import Fieldset, ModelAdmin
from polyadmin.fastapi.router import create_router
from polyadmin.ui import ui
from tests.conftest import csrf
from tests.core.test_model_admin import InMemoryUserAdmin


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
    from polyadmin.core.action import action
    from polyadmin.core.filter import BooleanFilter

    class FilterableAdmin(InMemoryUserAdmin):
        filters = [BooleanFilter("is_active")]

        @action
        def touch(self, objects, principal):
            return ""

    filterable = FilterableAdmin()
    filterable.create({"email": "jane@example.com"})
    admin = Admin(model_admins=[filterable])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app).get("/admin/users" + query).text


def test_filters_render_as_one_drawer_behind_one_trigger():
    page = _filterable_page()

    assert ui("toolbar", "filters") in page, "expected a toolbar filter cluster"
    assert 'aria-haspopup="dialog"' in page, "expected one Filters trigger opening a drawer"
    assert 'aria-label="Filters"' in page, "expected the drawer itself"
    assert "Is Active" in page, "expected the filter's label in the drawer"
    assert ui("sheet", "side-right") in page, "expected the drawer to come in from the right"


def test_filter_trigger_counts_only_applied_filters():
    count = ui("filter-panel", "count")
    assert count not in _filterable_page(), "expected no count badge while nothing is filtered"
    applied = _filterable_page("?filter[is_active]=true")
    assert count in applied, "expected a count badge once a filter is applied"


def test_reset_lives_in_the_drawer_and_only_when_something_is_applied():
    assert "Clear all" not in _filterable_page(), "expected no Reset while nothing is applied"
    applied = _filterable_page("?filter[is_active]=true")
    assert "Clear all" in applied, "expected Reset in the drawer once a filter is applied"


def test_toolbar_controls_fill_their_line_while_stacked():
    item = ui("toolbar", "item")
    page = _filterable_page()
    # search, the Filters trigger (wrapper + button), bulk actions
    # (form + button), Export, New.
    assert page.count(item) >= 6, (
        f"expected every stacked toolbar control to fill its line, found {page.count(item)}"
    )


def test_stacked_toolbar_controls_put_the_label_left_and_the_icon_right():
    label = ui("toolbar", "item-label")
    icon_class = ui("toolbar", "item-icon")
    page = _filterable_page()

    # Filters, the action select and Export each get a label that takes the
    # slack. New is deliberately icon-only and so is not one of them.
    assert page.count(label) >= 3, (
        f"expected each stacked control's label to take the slack, found {page.count(label)}"
    )
    # Filters' leading icon plus Export's icon+chevron move to the trailing
    # edge; the action select's chevron is already last and needs no reorder.
    assert page.count(icon_class) >= 3, (
        f"expected leading icons to move to the trailing edge, found {page.count(icon_class)}"
    )


def test_select_label_is_a_data_attribute_not_a_js_string_literal(task_client):
    page = task_client.get("/admin/tasks/1/edit").text

    assert 'x-data="adminSelect()"' in page, (
        "expected the x-data to be the bare factory call, with no interpolated label"
    )
    assert 'x-init="hydrate()"' in page, "expected the label to be hydrated from the DOM"
    assert 'data-label="Medium"' in page
    # The point of the whole arrangement: the label must never appear
    # inside the Alpine expression, only as an HTML attribute value.
    assert "label: 'Medium'" not in page and 'label: "Medium"' not in page, (
        "the label must not be interpolated into a JS string literal"
    )


def _boolean_client():
    user_admin = InMemoryUserAdmin()
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), user_admin


def test_boolean_cells_render_as_icons_with_an_accessible_label():
    client, user_admin = _boolean_client()
    user_admin.create({"email": "yes@example.com", "is_active": True})
    user_admin.create({"email": "no@example.com", "is_active": False})

    page = client.get("/admin/users").text

    # The check and cross path data, from components/icons.html.
    assert "M4.5 12.75l6 6 9-13.5" in page, "expected a check icon for a true boolean"
    assert "M6 18L18 6M6 6l12 12" in page, "expected a cross icon for a false boolean"
    assert '<span class="sr-only">Yes</span>' in page
    assert '<span class="sr-only">No</span>' in page
    # The old plain-text rendering is gone: the words survive only as
    # the sr-only labels asserted above.
    assert 'dark:text-emerald-400">Yes<' not in page


def test_boolean_export_is_unaffected_by_the_icon_rendering():
    client, user_admin = _boolean_client()
    user_admin.create({"email": "yes@example.com", "is_active": True})

    csv = client.get("/admin/users/export/csv").text
    assert "<svg" not in csv and "sr-only" not in csv, f"export leaked list markup: {csv}"
    assert "True" in csv or "true" in csv, f"expected the boolean as text in the export, got {csv}"


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


def test_list_renders_export_dropdown_rather_than_one_button_per_format():
    admin = Admin(model_admins=[InMemoryUserAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin/users").text

    assert 'aria-haspopup="menu"' in page, "expected the export DropdownMenu trigger"
    assert "/admin/users/export/csv" in page
    assert "/admin/users/export/xlsx" in page
    assert 'role="menuitem"' in page


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


def test_combobox_uses_token_classes():
    # The autocomplete relation field is the one genuinely Alpine-driven
    # form control; its panel/active-item classes must come from the
    # registry so it themes with everything else.
    assert "bg-popover" in ui("combobox", "content")
    # Applied/removed imperatively by the arrow-key handler, so it has to
    # stay a single class with no spaces.
    assert " " not in ui("combobox", "item-active")


def test_toast_viewport_sits_bottom_right_and_does_not_block_clicks():
    """The reference design system's ToastViewport, pinned bottom-right.
    pointer-events-none matters: record pages now carry a sticky action
    bar in that same corner, and the viewport spans a strip of the
    screen even with no toasts in it -- without it, Save would be
    unclickable."""
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


def test_select_is_keyboard_operable(task_client):
    page = task_client.get("/admin/tasks/1/edit").text

    for want in (
        '@keydown.down.prevent="openAndMove(1)"',
        '@keydown.up.prevent="openAndMove(-1)"',
        "@keydown.home.prevent=\"if (open) setActive(optionEls()[0])\"",
        # Focus stays on the trigger, so the trigger is what names the
        # highlighted option.
        ':aria-activedescendant="open ? activeId : null"',
        ":aria-controls=\"$id('select-listbox')\"",
    ):
        assert want in page, f"select is missing {want!r}"
    # tabindex="0" on every option would make Tab walk the whole list;
    # with a roving highlight the options must be out of the tab order.
    assert 'role="option" tabindex="0"' not in page, (
        "options must not be individually tabbable"
    )


def test_filter_drawer_traps_focus():
    # aria-modal="true" is a promise that focus cannot leave the drawer.
    assert 'x-trap="open"' in _filterable_page(), (
        "the filter drawer declares aria-modal but does not trap focus"
    )


class FieldsetTaskAdmin(TaskAdmin):
    fieldsets = [
        Fieldset(fields=["name"]),
        Fieldset(title="Scheduling", description="When it is due.", fields=["due_date"]),
        Fieldset(title="Advanced", fields=["priority"], collapsed=True),
    ]


@pytest.fixture
def fieldset_client():
    admin = Admin(model_admins=[FieldsetTaskAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_declared_fieldsets_render_as_titled_groups(fieldset_client):
    page = fieldset_client.get("/admin/tasks/1/edit").text
    for want in ("Scheduling", "When it is due.", "Advanced"):
        assert want in page, f"expected {want!r} in the form"
    # Every field still renders -- grouping must not drop any.
    for name in ('name="name"', 'name="due_date"', 'name="priority"'):
        assert name in page, f"field {name} went missing when grouped"


def test_collapsed_fieldset_starts_closed_and_others_open(fieldset_client):
    page = fieldset_client.get("/admin/tasks/1/edit").text
    assert 'x-data="{ open: false }"' in page, "expected the collapsed group to start closed"
    assert 'x-data="{ open: true }"' in page, "expected the uncollapsed titled group to start open"


def test_undeclared_fieldsets_render_no_group_chrome(task_client):
    # The default case must not gain a wrapper: an admin that declares no
    # fieldsets should render exactly the flat form it always did.
    page = task_client.get("/admin/tasks/1/edit").text
    assert ui("fieldset") not in page, (
        "a form with no declared fieldsets must render no fieldset chrome"
    )
    assert 'name="name"' in page, "the flat form still has to render its fields"


class ReadOnlyTaskAdmin(TaskAdmin):
    readonly_fields = ["name"]

    def update(self, obj, data):
        # Deliberately writes whatever it is handed: the protection has
        # to come from the framework not passing the value, not from the
        # application remembering to ignore it.
        if "name" in data:
            obj.name = data["name"]
        if "priority" in data:
            obj.priority = data["priority"]
        return obj


@pytest.fixture
def readonly_client():
    ma = ReadOnlyTaskAdmin()
    admin = Admin(model_admins=[ma])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app), ma


def test_readonly_field_is_refused_even_when_posted(readonly_client):
    # The one that matters: omitting the input is presentation, not
    # enforcement. A crafted POST must not be able to write the field.
    client, ma = readonly_client
    before = ma._item.name

    response = client.post(
        "/admin/tasks/1/edit",
        data={"name": "hacked", "due_date": "2026-03-14", "priority": "High"},
        headers=csrf(client),
        follow_redirects=False,
    )
    assert response.status_code < 400, f"expected the save to succeed, got {response.status_code}"
    assert ma._item.name == before, "a read-only field was written by a posted value"
    # The writable field on the same form must still save, or this is
    # just a broken form rather than a protected field.
    assert ma._item.priority == "High"


def test_readonly_field_renders_as_a_value_not_an_input(readonly_client):
    client, _ = readonly_client
    page = client.get("/admin/tasks/1/edit").text

    assert 'name="name"' not in page, "a read-only field must not render a posting input"
    assert "Ship it" in page, "expected the read-only field's value to still be shown"
    assert 'name="priority"' in page, "writable fields must still render inputs"


def test_boolean_field_renders_as_a_switch_inline_with_its_label():
    # A toggle beside its name, not a checkbox stacked under a label.
    from tests.fastapi.test_actions import make_client as make_action_client

    client, _ = make_action_client()
    page = client.get("/admin/users/create").text

    assert ui("field", "row") in page, (
        "expected the boolean field to lay its label and control on one row"
    )
    assert 'role="switch"' in page, "expected a switch, not a bare checkbox"
    # The control is still a native checkbox underneath, which is what
    # keeps it working with no JavaScript and posting like before.
    assert 'type="checkbox" id="field-is_active" name="is_active" value="true"' in page, (
        "the switch must still be a native checkbox posting the field's own name"
    )
    # Order matters and the assertions above would pass either way: the
    # switch sits to the left of the name it belongs to.
    assert page.index('id="field-is_active"') < page.index('for="field-is_active"'), (
        "expected the switch before its label, not after it"
    )


def test_non_boolean_fields_keep_the_stacked_layout(task_client):
    page = task_client.get("/admin/tasks/create").text
    assert ui("field", "row") not in page


class DescribedTaskAdmin(TaskAdmin):
    fields = [
        StringField("name", required=True, help_text="What the task is called."),
        DateField("due_date"),
        EnumField("priority", choices=["Low", "Medium", "High"]),
    ]


@pytest.fixture
def described_client():
    admin = Admin(model_admins=[DescribedTaskAdmin()])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app)


def test_field_description_shows_on_the_form(described_client):
    assert "What the task is called." in described_client.get("/admin/tasks/1/edit").text


def test_field_description_does_not_show_on_the_detail_page(described_client):
    assert "What the task is called." not in described_client.get("/admin/tasks/1").text


def test_field_without_a_description_renders_none(described_client):
    # Three fields, one of which has help text.
    page = described_client.get("/admin/tasks/1/edit").text
    assert page.count(ui("field", "description")) == 1


def _icon_path(name: str) -> str:
    """The `d` of one icon in components/icons.html, so a test can look
    for that glyph in a page without re-stating the path here."""
    from pathlib import Path

    import polyadmin

    source = (Path(polyadmin.__file__).parent / "templates/admin/components/icons.html").read_text()
    line = next(line for line in source.splitlines() if line.strip().startswith(f'"{name}":'))
    return line.split('"')[3]


def test_toasts_are_the_sonner_toaster():
    """The anatomy that makes these toasts Sonner's rather than a
    generic stack: its column geometry, a queue that can pause a toast's
    timer, an icon per level, and a close button with a name."""
    user_admin = InMemoryUserAdmin()
    user_admin.create({"email": "a@example.com"})
    admin = Admin(model_admins=[user_admin])
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin/users").text

    # Sonner's own measurements: 14px between toasts, and a 356px column
    # inside a 32px offset from the viewport's edge.
    toast_list = ui("toast", "list")
    for want in ("gap-[14px]", "sm:w-[420px]", "sm:p-8"):
        assert want in toast_list, f"the toast column is not Sonner's geometry: missing {want!r}"
    # The timer pauses while the pointer rests on a toast -- without a
    # queue that owns the timers, hovering could not hold one open.
    for want in ('x-data="adminToaster()"', '@mouseenter="pause(toast)"', '@mouseleave="resume(toast)"'):
        assert want in page, f"the toaster cannot pause a toast on hover: missing {want!r}"
    # One glyph per level, and none for a plain toast.
    assert _icon_path("check-circle") in page and _icon_path("x-circle") in page
    assert "x-show=\"toast.type !== 'default'\"" in page, (
        "a plain toast should carry no icon, as Sonner's does not"
    )
    # The close button used to be unlabelled, which left it nameless to
    # a screen reader.
    assert 'aria-label="Close"' in page, "the toast's close button has no accessible name"


def test_the_page_indicator_never_wraps():
    """The reference design system fixes the indicator at w-[100px],
    which a translated "Page 1 of 8" overflows in most languages --
    Russian's wrapped onto a second line, pushing the jump buttons out
    of the footer's row."""
    indicator = ui("pagination", "page-indicator")
    assert "min-w-[100px]" in indicator, f"the indicator's width is not a floor: {indicator!r}"
    assert "whitespace-nowrap" in indicator, f"a long translation can still wrap: {indicator!r}"
