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

```go
dashboard := &core.Dashboard{
	Title: "Overview",
	Widgets: []core.Widget{
		core.NewMetric("Users", func() any { return len(users.List()) }),
		core.NewDonut("Users by status", func() []core.ChartPoint {
			// ... count active/inactive, return []core.ChartPoint{{Label: "Active", Value: ...}, ...}
		}),
	},
}
admin := core.New(core.WithModelAdmins(...), core.WithDashboard(dashboard))
```

Every widget computes its own data lazily (`get_value`/`get_series`/
`get_rows`/`get_entries` callables in Python, plain functions in Go) —
nothing is computed until the dashboard route actually renders, so a
widget backed by a slow query only pays that cost on page load, not at
`Dashboard` construction time.

## Built-in widget types

| Widget | Shows | Python constructor | Go constructor |
|---|---|---|---|
| Metric | A single headline number | `Metric(title, get_value=...)` | `core.NewMetric(title, func() any)` |
| Stat | A headline number *and* its change vs. the previous period | `Stat(title, get_stat=...)` → `(value, delta)` | `core.NewStat(title, func() (any, float64))` |
| Progress | A value against a target, as a bar | `Progress(title, get_data=...)` → `(value, target)` | `core.NewProgress(title, func() (float64, float64))` |
| Chart | Labeled values as horizontal CSS bars | `Chart(title, get_series=...)` → `[(label, value), ...]` | `core.NewChart(title, func() []core.ChartPoint)` |
| Donut | A share-of-total breakdown, as an SVG ring + legend | `Donut(title, get_series=...)` → `[(label, value), ...]` | `core.NewDonut(title, func() []core.ChartPoint)` |
| Table | Small tabular data | `Table(title, columns=[...], get_rows=...)` | `core.NewTable(title, columns, func() []map[string]any)` |
| Activity | A recent-activity feed (short text entries) | `Activity(title, get_entries=...)` | `core.NewActivity(title, func() []string)` |
| Timeline | Dated events on a rail — time, title, description | `Timeline(title, get_entries=...)` → `[(time, title, description), ...]` | `core.NewTimeline(title, func() []core.TimelineEntry)` |
| Tabs | Several widgets in one card, one visible at a time | `Tabs(title, panels=[(label, widget), ...])` | `core.NewTabs(title, []core.TabPanel{...})` |

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
PinesUI/neutral palette as the rest of the framework.

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

```go
core.NewTabs("User breakdown", []core.TabPanel{
	{Label: "By status", Widget: core.NewDonut("Users by status", ...)},
	{Label: "By organization", Widget: core.NewDonut("Users by organization", ...)},
})
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

In Go, containers are a public extension point rather than a
`Tabs`-only special case: the adapter renders the panels of anything
implementing `core.Container` (`Widget` plus `Panels() []TabPanel`)
before that widget's own template runs, because `html/template` can't
execute a template whose name is only known at runtime. Nesting is
capped at 8 levels, so a container that transitively contains itself
fails with a clear error instead of exhausting the stack. In Python
the equivalent happens inside `tabs.html`, which renders each panel
through the same `{% include widget.template %}` the dashboard uses
for a top-level widget.

Every widget accepts `size="lg"`/`core.WithSize("lg")` to span the
full grid width instead of one column, and an optional
`permission=`/`core.WithPermission(...)`: a widget naming a permission
is simply omitted (not shown-disabled) if the `Authorizer` denies it
for the current principal — see [`permissions.md`](permissions.md).

## Custom widgets

Both languages let you add your own widget type without a framework
change.

Python: subclass `Widget`, set `template` to your own `.html` file
(placed under one of the `template_dirs` passed to `create_router`),
and implement `get_data()` — `{% include widget.template %}` resolves
it through Jinja2's normal loader search path, same as any other
override.

Go: implement the `Widget` interface (`Title()`, `Size()`,
`Permission()`, `Template()`, `GetData()`) for your own type, and pass
`fiberadapter.WithTemplateDirs(...)` to `Mount` with a file at
`{dir}/{your Template() value}` defining a block named after that same
value:

```go
// mywidget.go
type RecentSignupsWidget struct{ /* ... */ }

func (w RecentSignupsWidget) Template() string { return "widgets/recent-signups.html" }
// ... Title(), Size(), Permission(), GetData()
```

```gotemplate
{{/* templates/widgets/recent-signups.html */}}
{{define "widgets/recent-signups.html"}}
  <!-- your markup, using whatever GetData() returned -->
{{end}}
```

```go
fiberadapter.Mount(group, admin, "/admin", fiberadapter.WithTemplateDirs("templates"))
```

The framework's own widget templates (`Metric`, `Stat`, `Progress`,
`Chart`, `Donut`, `Table`, `Activity`, `Timeline`, `Tabs`) are checked
first, so a custom `Template()` value only needs to avoid colliding
with `admin/widgets/*.html` — see [`templates.md`](templates.md) for
the full resolution order shared with per-resource overrides.

A custom Go widget that nests other widgets only has to implement
`core.Container` on top of `Widget`; its template then receives
`{"Panels": [{Label, Body}]}`, with each `Body` the already-rendered
HTML of that panel's widget.
