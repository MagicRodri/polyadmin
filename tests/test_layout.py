"""The shared template layout. Mirrors go-polyadmin/fiber/layout_test.go."""

from pathlib import Path

import polyadmin

TEMPLATES = Path(polyadmin.__file__).parent / "templates"

# The two implementations' template trees are kept path-for-path
# identical, so a file that does a job in one repository has the same
# name and location in the other (docs/templates.md). Pinned as an
# explicit list rather than read from the Go tree -- the repos are
# separate checkouts, and the point is to fail when someone moves or
# adds a template on one side only.
SHARED_LAYOUT = {
    "admin/base.html",
    "admin/theme.html",
    "admin/login.html",
    "admin/dashboard.html",
    "admin/resource/list.html",
    "admin/resource/detail.html",
    "admin/resource/form.html",
    "admin/resource/delete.html",
    "admin/components/list_content.html",
    "admin/components/search.html",
    "admin/components/form_wrapper.html",
    "admin/components/inline.html",
    "admin/components/inline_fragment.html",
    "admin/components/lookup_results.html",
    "admin/components/toasts.html",
    "admin/components/action_confirm_modal.html",
    "admin/components/csrf-field.html",
    "admin/components/ui/breadcrumb.html",
    "admin/components/ui/bulk-actions.html",
    "admin/components/ui/calendar.html",
    "admin/components/ui/dropdown-menu.html",
    "admin/components/ui/field.html",
    "admin/components/ui/filter-panel.html",
    "admin/components/ui/multi-select.html",
    "admin/components/ui/pagination.html",
    "admin/components/ui/radio-group.html",
    "admin/components/ui/select.html",
    "admin/components/ui/sidebar.html",
    "admin/components/ui/slider.html",
    "admin/components/ui/switch.html",
    "admin/components/ui/table.html",
    "admin/components/ui/theme-toggle.html",
    "admin/widgets/activity.html",
    "admin/widgets/chart.html",
    "admin/widgets/donut.html",
    "admin/widgets/metric.html",
    "admin/widgets/progress.html",
    "admin/widgets/stat.html",
    "admin/widgets/table.html",
    "admin/widgets/tabs.html",
    "admin/widgets/timeline.html",
}

# Templates that exist only here, because Go builds the same HTML in Go
# code -- see the fiber package's doc comment on why field and form
# markup is assembled there rather than in html/template. Listed so the
# exception stays a deliberate two-file set rather than growing quietly.
PYTHON_ONLY = {
    "admin/components/icons.html",  # Go: fiber/icons.go
    "admin/components/field.html",  # Go: fiber/render_helpers.go
}


def _actual() -> set[str]:
    return {str(p.relative_to(TEMPLATES)) for p in TEMPLATES.rglob("*.html")}


def test_template_tree_matches_the_go_implementation_path_for_path():
    unexpected = _actual() - SHARED_LAYOUT - PYTHON_ONLY
    assert not unexpected, (
        f"templates exist but are not in the expected layout: {sorted(unexpected)} "
        "(add them to the Go tree at the same path, and to this list)"
    )
    missing = SHARED_LAYOUT - _actual()
    assert not missing, f"expected by the shared layout but missing here: {sorted(missing)}"


def test_python_only_templates_are_still_the_documented_exceptions():
    assert PYTHON_ONLY <= _actual(), "a documented Python-only template is gone"
