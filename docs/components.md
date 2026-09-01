# UI Components

The admin's design system is [shadcn/ui](https://ui.shadcn.com),
hand-ported to Alpine.js + Tailwind. This page is the reference for
what exists, how to use it from a template, and why each component was
ported the way it was.

Nothing here is an npm dependency. shadcn distributes component markup
as code you copy into your own project rather than a package you
install, which is what makes it usable from `html/template` at all — the
parts that don't come across (React, Radix UI, `cva`,
`tailwind-merge`) are reimplemented, not vendored. See
`plan/shadcnui-usage.md` for the full plan.

## The two things a template needs

### `ui` — class lists

`ui` is the server-side stand-in for shadcn's
[`class-variance-authority`](https://cva.style). shadcn resolves a
component's class list in JS at React render time; there is no JS render
step here, so the same lookup lives in [`fiber/ui.go`](../fiber/ui.go)
and resolves while the template executes.

```gotemplate
<button class="{{ui "button"}}">Save</button>
<button class="{{ui "button" "outline" "size-sm"}}">Cancel</button>
<button class="{{ui "button" "destructive"}}">Delete</button>
<th class="{{ui "table" "th"}}">Email</th>
```

Two kinds of modifier, and the difference matters:

| Kind | Behavior | Examples |
| --- | --- | --- |
| **variant** / **size** | *Composed* with the component's base, exactly like `cva`. Sizes are prefixed `size-`. | `ui "button" "ghost" "size-icon"` |
| **part** | *Replaces* the base. These are shadcn's sub-components — `CardTitle`, `TableHead`, `BreadcrumbLink` — which have their own class lists and are not variants of the parent. | `ui "card" "title"`, `ui "table" "cell"` |

Requesting a part alongside another modifier is an error, as is an
unknown component or modifier. Errors from a template func abort
`ExecuteTemplate`, so a typo fails loudly in the render tests instead of
shipping an unstyled control.

> **Why the split is load-bearing.** React-side `cva` runs its output
> through `tailwind-merge`, which drops conflicting utilities. There is
> no `tailwind-merge` here, so two competing utilities in one `class`
> attribute would resolve by Tailwind's own output order — not the order
> written. The registry therefore holds a rule by construction: a base
> never sets a property its own variants or sizes also set (which is why
> `button`'s base carries no height, padding, or background). Two tests
> pin it: `TestUIRegistryBaseDoesNotFightItsVariants` and
> `TestUIRegistryPartsUsableFromClassList`.

### `dict` / `list` — component partials

Components with real markup and behavior are `{{define "ui/..."}}`
partials under
[`templates/admin/components/ui/`](../templates/admin/components/ui/).
`{{template}}` accepts only one data value, so `dict` and `list` build
one:

```gotemplate
{{template "ui/dropdown-menu" dict
    "label" "Export" "icon" "download" "text" "Export"
    "items" (list
      (dict "Label" "CSV"  "URL" (printf "%s/%s/export/csv" .BasePath .Slug))
      (dict "Label" "XLSX" "URL" (printf "%s/%s/export/xlsx" .BasePath .Slug)))}}
```

Item lists are always *data*, never HTML strings, so a partial never has
to trust caller-supplied markup.

## Tokens and theming

Every color in the registry is a CSS variable declared in
[`templates/admin/theme.html`](../templates/admin/theme.html) — shadcn's
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
the palette is retuned in dark mode, and the Donut's `donutColors` names
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
| `select` | sizes `size-default/sm/auto` | The base class list, now used only as the trigger *button* of the styled Selects — `ui/select.html` for a single value and `ui/multi-select.html` (`size-auto`, so it grows as chips wrap) for a many-to-many. The native `<select>` it was named for survives only in the compact tabular-inline cells. |
| `label` | — | |
| `checkbox`, `radio` | — | Native, tinted with `accent-primary`. A custom listbox gains nothing over the native control here (no multi-item list, no search), so these stay native. |
| `switch` | parts `input`, `track`, `thumb` | A native checkbox styled as shadcn's Switch: `sr-only` input plus sibling track/thumb driven by `peer-checked:`, so it toggles with no JavaScript and posts like any checkbox. Used by generated boolean fields (inline with the label) and by custom pages via the `switch` wrapper. |
| `badge` | variants `default`, `secondary`, `destructive`, `outline` | Available; not yet used by a framework view. |
| `card` | parts `header`, `title`, `description`, `content`, `footer` | |
| `alert` | variants `default`, `destructive`; parts `title`, `description` | The form's non-field-error summary. |
| `separator` | variants `horizontal`, `vertical` | |
| `skeleton`, `avatar` | `avatar`: parts `image`, `fallback` | Available for custom pages. |
| `text` | parts `muted`, `muted-xs`, `empty`, `placeholder`, `heading`, `label-caps`, `metric`, `link`, `error` | Shared text roles, so "the muted small text" is one decision. |

### Overlays

| Component | Radix → Alpine | Where it's used |
| --- | --- | --- |
| `dialog` | Dialog → `x-teleport` + `x-trap.inert.noscroll` + `x-show`/`x-transition` | `admin/action_confirm_modal.html`, behind both bulk/record action confirmations and the row-delete `hx-confirm`. |
| `dropdown` | DropdownMenu; Floating UI → `x-anchor` | `ui/dropdown-menu`, used for the list view's Export menu. |
| `popover` | Popover; Floating UI → `x-anchor` | The date picker's calendar. |
| `tooltip` | Tooltip → CSS only (`peer-hover:`, `peer-focus-visible:`), so it works before Alpine loads | The theme toggle. |
| `toast` | Sonner | `admin/toasts.html` — a PinesUI-derived queue restyled onto the tokens. |
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
| `field` | shadcn's `FormItem`/`FormLabel`/`FormDescription`/`FormMessage`. Its markup lives in `ui/field.html`; `fiber/render_helpers.go`'s `formInputHTML` does the per-type derivation (stringifying values, matching selections) in Go and hands the result to that partial to print — see the partial's own doc comment for why no comparison logic lives in the template itself. |
| `combobox` | Radix Popover + `cmdk`, but the filtering stays **server-side**: `cmdk` filters a client array, whereas the whole point of `AutocompleteFieldNames` is never loading the target's dataset into the page. htmx owns the round trip to `/lookup`; Alpine owns open/close and arrow keys. Its `content`/`item` parts are also reused, unmodified, by `ui/select` and `ui/bulk-actions` below — the same popover/listbox look, just without a search box. |
| `select` (`ui/select.html`) | Radix Select — a styled trigger + listbox for a *static* choice list (enum fields, and a plain foreignkey/onetoone without `AutocompleteFieldNames`). A hidden input carries the posted value, same reasoning as the relation combobox above: the model layer never has to know a value came from anything but a plain `<select>`. Not used for many-to-many — that's `ui/multi-select.html` below. The list view's bulk-actions control (`ui/bulk-actions.html`) is the same trigger+listbox shape generalized to *run* an action on pick instead of holding a value. |
| `multi-select` (`ui/multi-select.html`) | The many-to-many control: a Command-style searchable list with the selection as removable chips — Django admin's `filter_horizontal` job, without the two-pane layout. Filtering is client-side, unlike the relation combobox, because a many-to-many's options are already all in the page. Posts one hidden input per selection under the field's name, which is what a `<select multiple>` posted, so the handler's `PeekMulti`/`getlist` is unchanged. |
| `calendar` | `ui/calendar` (the month grid) and `ui/date-picker` (a native `<input type="date">` plus the grid in a popover). There's no `react-day-picker`, so the grid is computed by the `adminCalendar` Alpine factory — always six weeks, like `fixedWeeks`. |
| `slider` | Native `<input type="range">` tinted with `accent-primary`; Alpine only drives the value readout. **Custom pages only.** |
| `radio-group` | Native radios. Radix rebuilds radio semantics on divs with a roving tabindex; the native control already has all of it and posts too. **Custom pages only.** |

## Using components on a custom page

A custom `AdminPage` ([`routing.md`](routing.md#custom-admin-pages))
gets the same components — the `ui` func and every `ui/*` partial are
parsed into every template set, including page templates resolved from
`WithTemplateDirs`. The example app's broadcast page
(`examples/fiber/templates/pages/broadcast.html`) is the worked
demonstration, and is where `switch`, `radio-group`, and `slider` are
exercised.

```gotemplate
{{define "content"}}
<form method="post" action="{{.BasePath}}/tools/broadcast" class="{{ui "panel" "form"}} max-w-xl">
  <div class="{{ui "field"}}">
    <label for="message" class="{{ui "field" "label"}}">Message</label>
    <div class="{{ui "field" "control"}}">
      <textarea id="message" name="message" class="{{ui "textarea"}}"></textarea>
    </div>
  </div>

  {{template "ui/switch" dict "name" "also_email" "label" "Also send by email" "checked" false}}
  {{template "ui/slider" dict "name" "rate" "label" "Throttle" "min" 10 "max" 500 "step" 10 "value" 100 "suffix" "/min"}}

  <button type="submit" class="{{ui "button"}}">Send</button>
</form>
{{end}}
```

Each of those posts as an ordinary form field, so the handler reads them
with `pc.C.FormValue` — no JSON body, no client-side state.

## Adding a component

1. Read the component's rendered DOM on ui.shadcn.com (the markup and
   class list), not its `.tsx` source.
2. Add its class lists to `uiRegistry` in [`fiber/ui.go`](../fiber/ui.go),
   splitting variants/sizes from parts, and keeping colors on tokens.
   Mirror the same keys into `python-polyadmin/polyadmin/ui.py` — a
   test in each language fails if one side gains a component the other
   lacks.
3. If it needs markup, add a `{{define "ui/<name>"}}` partial under
   `templates/admin/components/ui/`. It's picked up automatically by the
   `admin/components/ui/*.html` glob.
4. Swap the Radix primitive for its Alpine equivalent (`x-teleport`,
   `x-trap`, `x-anchor`, `x-collapse`, `@click.outside`,
   `@keydown.escape`) and keep every `aria-*`/`role` attribute from the
   reference markup verbatim — Radix's accessibility work is the part
   most worth keeping.
5. Add a render test. `fiber/components_test.go` is the pattern.
