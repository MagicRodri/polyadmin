"""Layout-level theming assertions -- mirrors go-polyadmin/fiber/theme_test.go."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polyadmin.core.admin import Admin
from polyadmin.core.dashboard import Dashboard
from polyadmin.fastapi.router import create_router
from tests.core.test_model_admin import InMemoryUserAdmin


@pytest.fixture
def page():
    """A rendered full page. The dashboard needs no fixtures, so it's the
    cheapest place to assert layout-level concerns."""
    admin = Admin(model_admins=[InMemoryUserAdmin()], dashboard=Dashboard())
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    return TestClient(app).get("/admin").text


@pytest.mark.parametrize(
    "token",
    [
        # The light palette on :root and the dark override, both as bare
        # HSL triplets so Tailwind's <alpha-value> opacity modifiers work.
        "--background: 0 0% 100%;",
        "--muted-foreground: 240 3.8% 46.1%;",
        "--radius: 0.5rem;",
        # Chart tokens are for *categorical data* (the Donut widget's
        # slices) as opposed to UI chrome -- the same split shadcn draws.
        # Without them a Donut would fall back to literal Tailwind
        # shades and stop following the theme.
        "--chart-1:",
        "--chart-6:",
        ".dark {",
        "--background: 240 10% 3.9%;",
    ],
)
def test_layout_emits_theme_tokens(page, token):
    assert token in page


@pytest.mark.parametrize(
    "fragment",
    [
        'darkMode: "class"',
        "hsl(var(--border) / <alpha-value>)",
        "hsl(var(--primary) / <alpha-value>)",
        "hsl(var(--chart-1) / <alpha-value>)",
        "var(--radius)",
    ],
)
def test_layout_configures_tailwind_for_tokens_and_dark_mode(page, fragment):
    assert fragment in page


def test_cdn_script_precedes_tailwind_config(page):
    # Order matters, and it's the order that isn't obvious: the CDN
    # script has to load *before* tailwind.config is assigned, since
    # loading it is what defines the `tailwind` global in the first
    # place. Assigning to it first throws a ReferenceError the browser
    # swallows silently -- confirmed with a real headless-Chrome run,
    # where getting this backwards left tailwind.config as {} and not
    # one token-based utility (.bg-background, .text-chart-1, ...)
    # existed in the generated stylesheet.
    assert page.index("cdn.tailwindcss.com") < page.index("tailwind.config")


def test_layout_resolves_theme_before_paint(page):
    # The class has to be set by a synchronous inline script before the
    # first paint, or a dark-mode reload flashes the light palette.
    assert 'localStorage.getItem("polyadmin-theme")' in page
    assert 'classList.toggle("dark", dark)' in page
    assert page.index('localStorage.getItem("polyadmin-theme")') < page.index("<body")


@pytest.mark.parametrize(
    "plugin", ["@alpinejs/focus", "@alpinejs/collapse", "@alpinejs/anchor"]
)
def test_layout_loads_alpine_plugins_before_alpine_core(page, plugin):
    # x-trap (the confirm dialog), x-collapse (the sidebar accordion),
    # and x-anchor (dropdown/date-picker popovers) all come from plugins,
    # and Alpine only registers directives that exist by the time core
    # initializes -- so plugins must load first.
    assert page.index(plugin) < page.index("unpkg.com/alpinejs@")


def test_layout_uses_token_classes_not_literal_palette(page):
    assert "bg-background" in page
    assert "text-foreground" in page
    # The <style>/<script> blocks legitimately mention the palette-free
    # HSL numbers, but no *class* should name a literal Tailwind shade.
    for banned in ("bg-neutral-", "text-neutral-", "border-neutral-", "bg-gray-"):
        assert banned not in page, f"rendered page still uses {banned}"


def test_layout_renders_theme_toggle(page):
    assert "$store.theme.toggle()" in page
    assert 'Alpine.store("theme"' in page
    assert 'aria-label="Toggle dark mode"' in page



def test_donut_slices_use_chart_tokens():
    """The Donut's palette lives in core (polyadmin/core/widget.py's
    _DONUT_COLORS) but must resolve through the theme, so a dashboard's
    categorical colors follow a retheme and get dark-mode-tuned values.
    """
    from polyadmin.core.widget import Donut

    admin = Admin(
        model_admins=[InMemoryUserAdmin()],
        dashboard=Dashboard(widgets=[Donut("Devices", series=[("Desktop", 60), ("Mobile", 40)])]),
    )
    app = FastAPI()
    app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
    page = TestClient(app).get("/admin").text

    assert "bg-chart-1" in page
    assert "text-chart-1" in page
    for banned in ("bg-blue-500", "text-blue-500", "bg-violet-500"):
        assert banned not in page, f"Donut still uses the literal palette {banned}"
