# UI Components

The admin's design system is [shadcn/ui](https://ui.shadcn.com),
hand-ported to Alpine.js + Tailwind. This page is the reference for
what exists, how to use it from a template, and why each component was
ported the way it was.

Nothing here is an npm dependency. shadcn distributes component markup
as code you copy into your own project rather than a package you
install, which is what makes it usable from Jinja2 at all — the
parts that don't come across (React, Radix UI, `cva`,
`tailwind-merge`) are reimplemented, not vendored. See
`plan/shadcnui-usage.md` for the full plan.

## The two things a template needs

### `ui` — class lists

`ui` is the server-side stand-in for shadcn's
[`class-variance-authority`](https://cva.style). shadcn resolves a
component's class list in JS at React render time; there is no JS render
step here, so the same lookup lives in [`polyadmin/ui.py`](../polyadmin/ui.py)
and resolves while the template executes.

```jinja
<button class="{{ ui('button') }}">Save</button>
<button class="{{ ui('button', 'outline', 'size-sm') }}">Cancel</button>
<button class="{{ ui('button', 'destructive') }}">Delete</button>
<th class="{{ ui('table', 'th') }}">Email</th>
```

Two kinds of modifier, and the difference matters:

| Kind | Behavior | Examples |
| --- | --- | --- |
| **variant** / **size** | *Composed* with the component's base, exactly like `cva`. Sizes are prefixed `size-`. | `ui('button', 'ghost', 'size-icon')` |
| **part** | *Replaces* the base. These are shadcn's sub-components — `CardTitle`, `TableHead`, `BreadcrumbLink` — which have their own class lists and are not variants of the parent. | `ui('card', 'title')`, `ui('table', 'cell')` |

Requesting a part alongside another modifier is an error, as is an
unknown component or modifier. An exception from a Jinja global aborts the render, so a typo fails loudly in the render tests instead of
shipping an unstyled control.

> **Why the split is load-bearing.** React-side `cva` runs its output
> through `tailwind-merge`, which drops conflicting utilities. There is
> no `tailwind-merge` here, so two competing utilities in one `class`
> attribute would resolve by Tailwind's own output order — not the order
> written. The registry therefore holds a rule by construction: a base
> never sets a property its own variants or sizes also set (which is why
> `button`'s base carries no height, padding, or background). Two tests
> pin it: `test_base_does_not_fight_its_variants` and
> `test_parts_are_usable_from_classlist`.

### `ui/*` macros — component partials

Components with real markup and behavior are Jinja macros under
[`polyadmin/templates/admin/components/ui/`](../polyadmin/templates/admin/components/ui/).
Import the macro, then call it with keyword arguments:

```jinja
{% from "admin/components/ui/dropdown-menu.html" import dropdown_menu %}

{{ dropdown_menu(
     "Export",
     icon_name="download",
     text="Export",
     items=[
       {"label": "CSV",  "url": base_path ~ "/" ~ slug ~ "/export/csv"},
       {"label": "XLSX", "url": base_path ~ "/" ~ slug ~ "/export/xlsx"},
     ],
   ) }}
```

Item lists are always *data*, never HTML strings, so a macro never has
to trust caller-supplied markup.

## Tokens and theming

Every color in the registry is a CSS variable declared in
[`polyadmin/templates/admin/theme.html`](../polyadmin/templates/admin/theme.html) — shadcn's
stock "Zinc" palette, as bare HSL triplets so Tailwind's
`<alpha-value>` opacity modifiers (`bg-primary/90`, `bg-muted/50`) work:

| Token | Use |
| --- | --- |
| `background` / `foreground` | page surface and its text |
| `card` / `card-foreground` | raised surfaces: panels, table shells, the sidebar |
| `popover` / `popover-foreground` | floating surfaces: menus, combobox panels, toasts |
| `primary` / `primary-foreground` | the main action, and the tooltip fill |
| `secondary` / `secondary-foreground` | a quieter filled control |
| `muted` / `muted-foreground` | table headers, help text, placeholders |
| `accent` / `accent-foreground` | hover and active states |
| `destructive` / `destructive-foreground` | delete actions, validation errors |
| `border` / `input` / `ring` | hairlines, control borders, focus rings |
| `chart-1` … `chart-6` | *categorical data* colors — the Donut widget's slices |
| `--radius` | corner radius, feeding `rounded-sm/md/lg` |

The `chart-*` set is deliberately separate from the chrome tokens above,
the same split shadcn draws: a slice color carries data, not hierarchy,
so it is spaced around the color wheel for distinguishability rather than
picked for contrast against a surface. It is still theme-owned, though —
the palette is retuned in dark mode, and the Donut's `_DONUT_COLORS` names
these tokens rather than literal shades, so a retheme restyles the
dashboard's charts too.

Two colors are *not* tokens, because shadcn has no token for them:
success (an emerald pair) and warning (an amber pair), used by the
boolean `Yes`, the Stat widget's delta, and the toast icons. Both name
an explicit `dark:` variant instead.

To restyle the admin, override `admin/theme.html` and change the
variables. Nothing else needs to know — see
[`templates.md`](templates.md#styling).

## Component reference

Everything below is used by the framework itself unless the last column
says otherwise.

### Primitives

| Component | Modifiers | Notes |
| --- | --- | --- |
| `button` | variants `default`, `destructive`, `destructive-outline`, `outline`, `secondary`, `ghost`, `link`, `ghost-destructive`, `ghost-muted`; sizes `size-default/sm/xs/lg/icon/icon-sm/icon-xs` | shadcn's six variants plus three of ours: `destructive-outline` for a detail page's Delete (matching the weight of the outline Edit beside it — solid `destructive` is reserved for the confirmation page's submit), `ghost-destructive` for a row's delete icon, `ghost-muted` for low-emphasis icon buttons. |
| `input` | sizes `size-default/sm`; part `bare` | Native. `bare` is for an input inside an already-bordered wrapper (the combobox). |
| `textarea` | size `size-default` | Native. |
| `select` | sizes `size-default/sm/auto` | The base class list, shared by two different controls: a native `<select multiple>` (`size-auto`, for manytomany fields, which still need the plain control — a multi-value combobox is a different component shadcn doesn't ship either) and, since `ui/select.html` (below), the trigger *button* of the styled single-value Select. |
| `label` | — | |
| `checkbox`, `radio` | — | Native, tinted with `accent-primary`. A custom listbox gains nothing over the native control here (no multi-item list, no search), so these stay native. |
| `switch` | parts `track`, `on`, `off`, `thumb`, `thumb-on`, `thumb-off` | A real Alpine port: `<button role="switch">` plus a hidden input so it still posts. **Custom pages only** — generated boolean fields use a checkbox. |
| `badge` | variants `default`, `secondary`, `destructive`, `outline` | Available; not yet used by a framework view. |
| `card` | parts `header`, `title`, `description`, `content`, `footer` | |
| `alert` | variants `default`, `destructive`; parts `title`, `description` | The form's non-field-error summary. |
| `separator` | variants `horizontal`, `vertical` | |
| `skeleton`, `avatar` | `avatar`: parts `image`, `fallback` | Available for custom pages. |
| `text` | parts `muted`, `muted-xs`, `empty`, `placeholder`, `heading`, `label-caps`, `metric`, `link`, `error` | Shared text roles, so "the muted small text" is one decision. |

### Overlays

| Component | Radix → Alpine | Where it's used |
| --- | --- | --- |
| `dialog` | Dialog → `x-teleport` + `x-trap.inert.noscroll` + `x-show`/`x-transition` | `admin/components/action_confirm_modal.html`, behind both bulk/record action confirmations and the row-delete `hx-confirm`. |
| `dropdown` | DropdownMenu; Floating UI → `x-anchor` | `ui/dropdown-menu`, used for the list view's Export menu. |
| `popover` | Popover; Floating UI → `x-anchor` | The date picker's calendar. |
| `tooltip` | Tooltip → CSS only (`peer-hover:`, `peer-focus-visible:`), so it works before Alpine loads | The theme toggle. |
| `toast` | Sonner | `admin/components/toasts.html` — a PinesUI-derived queue restyled onto the tokens. |
| `sheet` | Dialog + slide transition | The sidebar below `md`. |

### Navigation and data

| Component | Notes |
| --- | --- |
| `sidebar`, `nav-item` | One element is both the static `md:` column and the mobile sheet, so there's no duplicate nav markup. |
| `accordion` | The sidebar's category groups. Radix animates collapse with a `tailwindcss-animate` keyframe pair; there's no plugin here, so `x-collapse` does it — and needs no fixed height. |
| `breadcrumb` | Markup-only in shadcn too. Doubles as the page header. |
| `pagination` | Prev/next button group plus a record count. |
| `table` | Parts `wrapper`, `scroll`, `head`, `th`, `body`, `row`, `cell`, `empty`, and `th-compact`/`cell-compact` for tables nested in a card (the Table widget, tabular inlines). |
| `tabs` | Pill flavor (`list`, `trigger`, `trigger-on/off`) and an underline flavor (`underline-*`) used by the dashboard's Tabs widget, where a pill row would fight the card around it. |
| `widget`, `panel` | The dashboard card and the generic bordered surface. |

### Forms and advanced

| Component | Notes |
| --- | --- |
| `field` | shadcn's `FormItem`/`FormLabel`/`FormDescription`/`FormMessage`. Wraps every generated input — its `render_form_input` macro does the per-type dispatch directly (Jinja's `in`/`==` operators handle the comparisons natively, unlike Go's template language — see go-polyadmin's version of this file for why that side precomputes everything instead). |
| `combobox` | Radix Popover + `cmdk`, but the filtering stays **server-side**: `cmdk` filters a client array, whereas the whole point of `autocomplete_fields` is never loading the target's dataset into the page. htmx owns the round trip to `/lookup`; Alpine owns open/close and arrow keys. Its `content`/`item` parts are also reused, unmodified, by `ui/select` and `ui/bulk-actions` below — the same popover/listbox look, just without a search box. |
| `select` (`ui/select.html`) | Radix Select — a styled trigger + listbox for a *static* choice list (enum fields, and a plain foreignkey/onetoone without `autocomplete_fields`). A hidden input carries the posted value, same reasoning as the relation combobox above: the model layer never has to know a value came from anything but a plain `<select>`. Not used for `<select multiple>` (manytomany) — see the `select` primitive's own note. The list view's bulk-actions control (`ui/bulk-actions.html`) is the same trigger+listbox shape generalized to *run* an action on pick instead of holding a value. |
| `calendar` | `ui/calendar` (the month grid) and `ui/date-picker` (a native `<input type="date">` plus the grid in a popover). There's no `react-day-picker`, so the grid is computed by the `adminCalendar` Alpine factory — always six weeks, like `fixedWeeks`. |
| `slider` | Native `<input type="range">` tinted with `accent-primary`; Alpine only drives the value readout. **Custom pages only.** |
| `radio-group` | Native radios. Radix rebuilds radio semantics on divs with a roving tabindex; the native control already has all of it and posts too. **Custom pages only.** |

## Using components on a custom page

A custom `AdminPage` ([`routing.md`](routing.md#custom-admin-pages))
gets the same components — the `ui` global is registered on the Jinja environment, and every
`ui/*` macro is importable from any template the loader can reach --
including page templates resolved from `template_dirs`. The example app's broadcast page
(`examples/fastapi/templates/pages/broadcast.html`) is the worked
demonstration, and is where `switch`, `radio-group`, and `slider` are
exercised.

```jinja
{% extends "admin/base.html" %}
{% from "admin/components/ui/switch.html" import switch %}
{% from "admin/components/ui/slider.html" import slider %}
{% block content %}
<form method="post" action="{{ base_path }}/tools/broadcast" class="{{ ui('panel', 'form') }} max-w-xl">
  <div class="{{ ui('field') }}">
    <label for="message" class="{{ ui('field', 'label') }}">Message</label>
    <div class="{{ ui('field', 'control') }}">
      <textarea id="message" name="message" class="{{ ui('textarea') }}"></textarea>
    </div>
  </div>

  {{ switch("also_email", "Also send by email", checked=False) }}
  {{ slider("rate", "Throttle", min=10, max=500, step=10, value=100, suffix="/min") }}

  <button type="submit" class="{{ ui('button') }}">Send</button>
</form>
{% endblock %}
```

Each of those posts as an ordinary form field, so the handler reads them
with `await ctx.form()` — no JSON body, no client-side state.

## Adding a component

1. Read the component's rendered DOM on ui.shadcn.com (the markup and
   class list), not its `.tsx` source.
2. Add its class lists to `UI_REGISTRY` in [`polyadmin/ui.py`](../polyadmin/ui.py),
   splitting variants/sizes from parts, and keeping colors on tokens.
   Mirror the same keys into `go-polyadmin/fiber/ui.go` — a
   test in each language fails if one side gains a component the other
   lacks.
3. If it needs markup, add a macro under
   `polyadmin/templates/admin/components/ui/`. Import it where it's used.
4. Swap the Radix primitive for its Alpine equivalent (`x-teleport`,
   `x-trap`, `x-anchor`, `x-collapse`, `@click.outside`,
   `@keydown.escape`) and keep every `aria-*`/`role` attribute from the
   reference markup verbatim — Radix's accessibility work is the part
   most worth keeping.
5. Add a render test. `tests/fastapi/test_components.py` is the pattern.
