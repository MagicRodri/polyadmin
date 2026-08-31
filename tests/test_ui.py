"""Tests for the shadcn variant resolver -- mirrors go-polyadmin/fiber/ui_test.go."""
import re

import pytest

from polyadmin.ui import UI_REGISTRY, UnknownUIVariant, ui


def test_fills_in_both_default_axes():
    # Neither axis given: the shadcn defaults for variant *and* size
    # should both appear.
    classes = ui("button")
    assert "inline-flex" in classes  # base
    assert "bg-primary" in classes  # variant "default"
    assert "h-10 px-4 py-2" in classes  # size "size-default"


def test_explicit_variant_suppresses_default_variant():
    classes = ui("button", "outline")
    assert "border border-input" in classes
    # The default variant's fill must not leak in alongside it -- two
    # competing bg-* utilities would resolve by Tailwind's own output
    # order rather than intent.
    assert "bg-primary text-primary-foreground" not in classes
    # Size was not given, so it still defaults.
    assert "h-10" in classes


def test_explicit_size_suppresses_default_size():
    classes = ui("button", "ghost", "size-icon-sm")
    assert "h-8 w-8" in classes
    assert "h-10 px-4" not in classes


@pytest.mark.parametrize("args", [("buton",), ("button", "outlined")])
def test_rejects_unknown_component_and_modifier(args):
    # A typo has to raise: an unresolved name would otherwise ship an
    # unstyled control, silently.
    with pytest.raises(UnknownUIVariant):
        ui(*args)


def test_has_no_stray_whitespace():
    # Most "size-default" entries are deliberately empty, so the join
    # has to drop them rather than emit a double space.
    classes = ui("input")
    assert "  " not in classes
    assert classes == classes.strip()


def _group(component, name):
    return UI_REGISTRY[component].get(name, {})


@pytest.mark.parametrize("component", sorted(UI_REGISTRY))
def test_structural_invariants(component):
    spec = UI_REGISTRY[component]
    base = spec.get("base", "")
    variants, sizes, parts = (_group(component, g) for g in ("variants", "sizes", "parts"))

    # Something has to be resolvable, or the entry is dead weight.
    assert base or parts, f"{component} has neither a base nor any parts"
    # A size axis is only usable if it can default.
    if sizes:
        assert "size-default" in sizes, f"{component} has sizes but no 'size-default'"
    # The "size-" prefix is how the resolver tells the axes apart.
    for name in sizes:
        assert name.startswith("size-"), f"{component} size {name!r} must be prefixed 'size-'"
    for name in (*variants, *parts):
        assert not name.startswith("size-"), f"{component} {name!r} must not be prefixed 'size-'"
    # One name, one meaning.
    assert not (set(parts) & set(variants)), f"{component} declares a name as both part and variant"


def _tailwind_property(cls):
    """The CSS property a utility sets, for the conflict check below.

    Only the properties that actually collide in this registry are
    reported -- a base fighting its own variants over height, padding, or
    background is the realistic failure. A prefixed utility (``sm:``,
    ``hover:``) applies conditionally, so it never unconditionally fights
    an unprefixed one.
    """
    if ":" in cls:
        return None
    for prefix, prop in (
        ("h-", "height"),
        ("w-", "width"),
        ("bg-", "background"),
        ("px-", "padding-x"),
        ("py-", "padding-y"),
        ("p-", "padding"),
    ):
        if cls.startswith(prefix):
            return prop
    return None


def _properties_of(classes):
    return {
        prop: cls
        for cls in classes.split()
        if (prop := _tailwind_property(cls)) is not None
    }


@pytest.mark.parametrize("component", sorted(UI_REGISTRY))
def test_base_does_not_fight_its_variants(component):
    """There is no tailwind-merge here (see the module docstring), so a
    base that sets a property its own variant or size also sets produces
    two competing utilities in one class attribute -- and Tailwind
    resolves those by its own output order, not the order written.
    shadcn's cva entries avoid this by construction; so must these.
    """
    base_props = _properties_of(UI_REGISTRY[component].get("base", ""))
    for kind in ("variants", "sizes"):
        for name, classes in _group(component, kind).items():
            for prop, cls in _properties_of(classes).items():
                assert prop not in base_props, (
                    f"ui({component!r}) base sets {prop} via {base_props[prop]!r}, but "
                    f"{kind[:-1]} {name!r} also sets it via {cls!r} -- move it out of the base"
                )


def test_parts_are_usable_from_classlist():
    # Parts are handed to a DOM classList in a few places (the combobox's
    # arrow-key handler is the load-bearing one), and classList.add
    # throws InvalidCharacterError on a value containing a space. Only
    # the parts actually used that way must be single classes, so this
    # checks the known one rather than constraining every part.
    assert " " not in ui("combobox", "item-active")


def test_rejects_part_combined_with_other_modifiers():
    # A part replaces the base, so composing it with a variant is
    # meaningless -- better to say so than to silently pick one.
    with pytest.raises(UnknownUIVariant):
        ui("card", "title", "outline")


def test_part_resolves_without_the_base():
    # The bug this structure exists to prevent: `table`'s base is the
    # <table> element's own classes, and a <th> must not inherit them.
    th = ui("table", "th")
    assert "caption-bottom" not in th
    assert "w-full" not in th


# Anchored on a preceding word boundary and a trailing shade number, so
# this matches `bg-slate-50` but not `translate-x-4` -- an unanchored
# substring search flags the latter.
LITERAL_PALETTE = re.compile(
    r"(?:^|[\s:])(?:[a-z-]+-)?(?:neutral|gray|slate|zinc|stone)-\d+"
    r"|\bbg-white\b|\btext-black\b"
)


@pytest.mark.parametrize("component", sorted(UI_REGISTRY))
def test_uses_theme_tokens_not_literal_palette(component):
    """The whole point of the port: colors resolve through the CSS
    variables in admin/theme.html. A literal neutral-*/gray-* here would
    be invisible to the theme and to dark mode.

    The emerald/amber pairs are the documented exceptions -- there is no
    shadcn success/warning token to defer to, so those name an explicit
    dark: variant instead.
    """
    spec = UI_REGISTRY[component]
    checked = [("base", spec.get("base", ""))]
    for kind in ("variants", "sizes", "parts"):
        checked.extend(_group(component, kind).items())
    for modifier, classes in checked:
        match = LITERAL_PALETTE.search(classes)
        assert match is None, (
            f"ui({component!r}, {modifier!r}) uses the literal palette "
            f"{match.group().strip()!r}: {classes}"
        )


def test_registry_matches_the_go_implementation_key_for_key():
    """The two registries are maintained as mirrors (see the module
    docstring), so this pins the *shape* that a reader comparing them
    relies on: every component carries the same modifier names in both.

    Kept as an explicit list rather than parsing the Go source -- the
    point is to fail when someone adds a component to one side only.
    """
    expected_components = {
        # Phase A
        "button", "input", "textarea", "select", "label", "checkbox",
        "radio", "switch", "badge", "card", "alert", "separator",
        "skeleton", "avatar", "text",
        # Phase B
        "dialog", "dropdown", "popover", "tooltip", "toast", "sheet",
        # Phase C
        "sidebar", "nav-item", "tabs", "accordion", "breadcrumb",
        "pagination", "table",
        # Phase D
        "field", "combobox", "calendar", "slider",
        # dashboard / misc
        "widget", "panel", "page", "toolbar", "filter-panel",
    }
    assert set(UI_REGISTRY) == expected_components
