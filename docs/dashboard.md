# Dashboard

`Dashboard` renders at `GET {base_path}` — it's independent of any one
`ModelAdmin`, just a titled collection of `Widget`s.

```python
from polyadmin.core.dashboard import Dashboard
from polyadmin.core.widget import Metric, Donut, Table

dashboard = Dashboard(title="Overview", widgets=[
    Metric("Users", get_value=lambda: len(users.list())),
    Donut("Users by status", get_series=lambda: [
        ("Active", sum(1 for u in users.list() if u.is_active)),
        ("Inactive", sum(1 for u in users.list() if not u.is_active)),
    ]),
])
admin = Admin(model_admins=[...], dashboard=dashboard)
```

Every widget computes its own data lazily (`get_value`/`get_series`/
`get_rows`/`get_entries` callables) — nothing is computed until the
dashboard route actually renders, so a widget backed by a slow query
only pays that cost on page load, not at `Dashboard` construction time.

## How tall a card gets

The dashboard is a grid, and a grid stretches every card in a row to
match the tallest one. So a card's content area is bounded rather than
free to grow: past about 320px it scrolls inside its own card, with the
same themed scrollbar the rest of the admin uses. A `Table` of two
hundred rows leaves the cards beside it exactly where they were.

It scrolls in one direction only. A card is a fixed column of the grid,
so anything wider than it is a widget that has to wrap, not a sideways
scrollbar for the reader to drag — `widgets/table.html` wraps its cells
(and breaks a long unbroken value) rather than holding them on one
line.

This applies to a custom widget's template too — it renders inside that
box and needs no overflow container of its own. A second scroller
nested in there shows a second scrollbar, and content that bleeds past
the box's edge, as a negative margin does, is clipped.

## Built-in widget types

| Widget | Shows | Constructor |
|---|---|---|
| Metric | A single headline number | `Metric(title, get_value=...)` |
| Stat | A headline number *and* its change vs. the previous period | `Stat(title, get_stat=...)` → `(value, delta)` |
| Progress | A value against a target, as a bar | `Progress(title, get_data=...)` → `(value, target)` |
| Chart | Labeled values as horizontal CSS bars | `Chart(title, get_series=...)` → `[(label, value), ...]` |
| Donut | A share-of-total breakdown, as an SVG ring + legend | `Donut(title, get_series=...)` → `[(label, value), ...]` |
| Table | Small tabular data | `Table(title, columns=[...], get_rows=...)` |
| Activity | A recent-activity feed (short text entries) | `Activity(title, get_entries=...)` |
| Timeline | Dated events on a rail — time, title, description | `Timeline(title, get_entries=...)` → `[(time, title, description), ...]` |
| Tabs | Several widgets in one card, one visible at a time | `Tabs(title, panels=[(label, widget), ...])` |
| MetricGroup | A row of headline numbers from one data call | `MetricGroup(title, get_tiles=...)` → `[Tile(label, value, icon=, hint=), ...]` |
| DataTable | Paged, searchable rows fetched by the host | `DataTable(title, columns=[Column(...)], get_rows=...)` → `Rows(items, total=, totals=)` |

`Chart` and `Donut` are deliberately dependency-free — no JS charting
library is bundled (matching the CDN-only frontend approach), so
`Chart` renders as plain CSS width-percentage bars and `Donut` as a
hand-built SVG ring (the classic `stroke-dasharray`-on-a-circumference-
100-circle technique), not a real charting library's canvas/SVG
output. `Donut` cycles through a 6-color qualitative palette
(blue/violet/teal/amber/rose/cyan, deliberately distinct from the
toast component's green/orange/red success/warning/danger colors so a
slice is never mistaken for a status indicator); past 6 series entries
it wraps and repeats.

`Stat`, `Timeline` and `Tabs` are adapted from Flowbite's
admin-dashboard layout (its "Sales this week", "Latest Activity" and
"Statistics this month" cards respectively), restyled to the same
shadcn/ui tokens as the rest of the framework, so a custom widget
inherits the active theme (and dark mode) for free.

`Stat`'s delta is the *signed* percentage change, so `-4.2` means
"down 4.2%". The widget draws up in green and down in red, matching
the success/danger colors of the toast component, with an arrow
carrying the same meaning for anyone who can't separate the two hues.
That assumes up is good — for a metric where it isn't, such as an
error rate, negate the delta and say so in the title.

## Tabs: widgets inside widgets

`Tabs` is a *container*: it holds no data of its own, and each panel
is an ordinary widget rendered exactly as it would be at the top
level.

```python
Tabs("User breakdown", panels=[
    ("By status", Donut("Users by status", get_series=...)),
    ("By organization", Donut("Users by organization", get_series=...)),
])
```

Two things worth knowing:

- **Every panel is computed and rendered on page load**, not on first
  click — switching tabs is pure client-side Alpine, with no round
  trip, so a panel backed by a slow query costs the same whether or
  not anyone opens it. Put an expensive breakdown in its own widget
  rather than a tab if you don't want to pay for it every render.
- **A panel widget's own title isn't shown** — the tab label takes its
  place, and only the container's title appears in the card header.

With Alpine still loading (or not running at all), the first panel
stays visible and the rest stay hidden, so the card degrades to its
default tab rather than to everything-at-once.

Nesting happens inside `tabs.html`, which renders each panel through
the same `{% include widget.template %}` the dashboard uses for a
top-level widget — so a container is just a widget whose template
happens to include others.

Every widget accepts `size="lg"` to span the full grid width instead of
one column, and an optional `permission=`: a widget naming a permission
is simply omitted (not shown-disabled) if the `Authorizer` denies it
for the current principal — see [`permissions`](permissions.md).

## Filters

A dashboard can carry a filter bar. Each filter reads its own query
parameters, so a filtered dashboard is a plain URL you can reload or share.

```python
from polyadmin.core.dashboard import Dashboard, DateRangeFilter, SelectFilter

dashboard = Dashboard(
    title="Statistics",
    filters=[
        DateRangeFilter("period", label="Period", default_days=30),
        SelectFilter("contract_id", label="Client", empty_label="All clients", get_choices=load_contracts),
    ],
    widgets=[...],
)
```

| Filter | Query parameters | Value in `ctx.filters` |
|---|---|---|
| `DateRangeFilter(name, default_days=30)` | `{name}_from`, `{name}_to` (ISO dates) | `DateRange(start, end)` |
| `SelectFilter(name, choices=... \| get_choices=...)` | `{name}` | the chosen value, or `None` |

`SelectFilter(..., searchable=True)` puts a search box in the open list that
narrows the choices by label as you type, for a long list such as clients.

A filter never fails on what it is given: an unreadable date falls back to
the default range and a reversed range is swapped. `get_choices` may be sync
or async and is only called to render the page; a widget's request passes
the chosen value through without checking it against the choices.

## Widgets that depend on the request

A widget whose data function takes a context, or is `async`, is loaded
after the page, from `GET {base_path}/_widgets/{key}`, so a slow service
never holds up the whole dashboard. The context is a `WidgetContext`:

| Field | What |
|---|---|
| `filters` | every filter's parsed value, by name |
| `principal` | the signed-in principal |
| `search` | the widget's own search box, if it has one |
| `offset`, `limit` | the page a `DataTable` is asking for |

The widgets that take no context — every built-in one listed above except
`MetricGroup` and `DataTable` — keep rendering with the page, as before.

Options every widget takes:

- `key` — the widget's URL slug. Defaults to a slug of the title
  (transliterated, so Cyrillic titles work); pass it explicitly to keep URLs
  stable when a title changes. Keys must be unique within a dashboard.
- `depends_on` — the filters the widget reloads on. The default reloads on
  every filter; `[]` never reloads. Changing a filter re-fetches only the
  widgets that depend on it.
- `description` — a subtitle, or a callable of the `DashboardContext`, e.g.
  the period being shown.
- `empty_text` — shown when the widget has nothing to show.
- `size="full"` spans the whole row.
- `placement="top"` renders the widget above the filter bar, full width and
  without its card header -- a summary row such as the headline numbers.

## MetricGroup

Several numbers that one call answers:

```python
async def overview(ctx):
    data = await analytics.overview()
    return [
        Tile("Contracts", data["contracts"], icon="file-text"),
        Tile("Using the portal", data["active"], icon="activity", hint=f"dormant: {data['dormant']}"),
    ]

MetricGroup("Overview", key="overview", size="full", depends_on=[], get_tiles=overview)
```

## DataTable

Rows the host fetches a page at a time, e.g. from another service:

```python
async def passages(ctx):
    data = await analytics.passages(period=ctx.filters["period"], limit=ctx.limit, offset=ctx.offset)
    return Rows(data["items"], total=data["total"], totals=data["overall"])

DataTable(
    "Passages", key="passages", size="full",
    columns=[
        Column("contract", "Contract", strong=True),
        Column("total", "Total", align="end", format="number"),
        Column("keypass", "By key", align="end", format="share"),
    ],
    get_rows=passages, page_size=50, searchable=True, total_label="{total} contracts",
)
```

- `Rows(items, total=None, totals=None)`: `items` are dicts keyed by column
  key. `totals`, returned with the first page, is a bold summary row pinned
  above it. With `total` the table knows when it has shown everything;
  without it, a page shorter than `page_size` is the last.
- Scrolling to the last row loads the next page. `page_size=None` loads
  everything at once.
- `searchable=True` adds a search box to the card; its text arrives as
  `ctx.search`.
- `total_label` is a footer with `{total}` filled in.

| `format` | Value | Renders |
|---|---|---|
| `text` | anything | as is |
| `number` | int or float | in the viewer's locale |
| `datetime` | datetime or ISO string | in the viewer's locale and time zone |
| `share` | `{"count": 12, "percentage": 34.5}` | `12 (34.5%)`; just `0` when the count is 0 |
| `percent` | a number | `87.3%` |

`empty="never used"` on a column shows that text as a badge in an empty
cell instead of a dash. It goes through translation like other labels.

`tones=((80, "success"), (50, "warning"), (0, "danger"))` colours a numeric
cell: it renders as a badge in the colour of the highest minimum the value
reaches, and stays plain below all of them.

### Filter-aware donuts and tabs

A `Donut` whose `get_series` takes the context, or is `async`, loads from its
fragment route like `DataTable`. A `Tabs` loads that way as soon as one of its
panels does, so a card of breakdowns can follow the filters:

```python
Tabs("Breakdowns", key="breakdowns", size="full", panels=[
    ("Entry methods", Donut("Entry methods", get_series=passage_methods)),
    ("Users by role", Donut("Users by role", get_series=users_by_role)),
])
```

## When a widget fails

Raise `WidgetUnavailable("The analytics service is down.")` from a data
function to show that message in the widget's card. Any other exception
shows "This section is unavailable." and is logged; either way the other
widgets load normally. A request that never reaches the admin shows
"Couldn't load this section." with a Retry button.

## Exports

A dashboard export is a button on the filter bar that submits the current
filters to `GET {base_path}/_exports/{name}`:

```python
from polyadmin import Download
from polyadmin.core.dashboard import DashboardExport

async def export_statistics(ctx):
    workbook = await build_workbook(period=ctx.filters["period"])
    return Download("statistics.xlsx", XLSX_CONTENT_TYPE, content=workbook)

Dashboard(..., exports=[DashboardExport("xlsx", label="Export to Excel", handler=export_statistics)])
```

The handler receives a `DashboardContext` (`filters`, `principal`) and must
return a `Download`. It requires the `dashboard.export` permission unless
you pass another `permission=`; without it the button is hidden and the
route answers 403.

## Routes

| Route | Serves |
|---|---|
| `GET {base_path}` | the page: filter bar, exports, a card per widget |
| `GET {base_path}/_widgets/{key}` | one widget's body; rows only when `offset` > 0 |
| `GET {base_path}/_exports/{name}` | an export's file |

All of them require `dashboard.view`. A widget hidden by its `permission`
answers 404 on its route, as an unknown key does.

## Custom widgets

You can add your own widget type without a framework change. Subclass
`Widget`, set `template` to your own `.html` file (placed under one of
the `template_dirs` passed to `create_router`), and implement
`get_data()` — `{% include widget.template %}` resolves it through
Jinja2's normal loader search path, same as any other override.

```python
class RecentSignupsWidget(Widget):
    template = "widgets/recent-signups.html"

    def get_data(self):
        return {"rows": recent_signups()}
```

```jinja
{# templates/widgets/recent-signups.html #}
<!-- your markup, using whatever get_data() returned -->
```

```python
create_router(admin, base_path="/admin", template_dirs=["templates"])
```

The framework's own widget templates (`Metric`, `Stat`, `Progress`,
`Chart`, `Donut`, `Table`, `Activity`, `Timeline`, `Tabs`) are checked
first, so a custom `template` value only needs to avoid colliding with
`admin/widgets/*.html` — see [`templates`](templates.md) for the
full resolution order shared with per-resource overrides.
