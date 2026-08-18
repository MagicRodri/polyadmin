# Routing

How an `Admin` becomes actual HTTP routes, and what routes get
generated per `ModelAdmin`.

## Mounting

**Python**, an `APIRouter` you include yourself:

```python
from fastapi import FastAPI
from polyadmin.fastapi.router import create_router

app = FastAPI()
app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
```

**Go**, a group you mount onto:

```go
app := fiber.New()
group := app.Group("/admin")
if err := fiberadapter.Mount(group, admin, "/admin"); err != nil {
	log.Fatal(err)
}
```

In both, `base_path`/`basePath` must match the actual mount prefix —
it's used to build every link the templates render (nav, pagination,
redirects, the relation lookup URL) and isn't derived from the
router/group automatically, since the router is built before the host
framework knows where it'll end up mounted.

## Generated routes

For each registered `ModelAdmin`, gated by its own
`can_view`/`can_create`/`can_update`/`can_delete`/`can_export` flags
(`CanView()`/... in Go, backed by `Disable*` struct fields on
`BaseModelAdmin`):

| Method | Path | Requires | Purpose |
|---|---|---|---|
| GET | `/{slug}` | `.view` | List (search/filter/sort/paginate) |
| GET, POST | `/{slug}/create` | `.create` | Create form |
| GET | `/{slug}/{pk}` | `.view` | Detail |
| GET, POST | `/{slug}/{pk}/edit` | `.update` | Edit form |
| GET, POST, DELETE | `/{slug}/{pk}/delete` | `.delete` | Delete confirmation / non-HTMX delete / HTMX inline delete |
| GET | `/{slug}/lookup` | `.view` | Relation-autocomplete search fragment |
| POST | `/{slug}/actions/{name}` | `.view` (+ the action's own `permission`, if set) | Run a record/bulk Action — only registered if the `ModelAdmin` declares any |
| GET | `/{slug}/export/{format}` | `.export` | Streamed export — `csv`, plus `xlsx` in Python |
| POST | `/{slug}/{pk}/inlines/{child_slug}` | parent `.update` + child `.create` | Create one inline child row — only registered if the `ModelAdmin` declares any `inlines` |
| POST | `/{slug}/{pk}/inlines/{child_slug}/{child_pk}` | parent `.update` + child `.update` | Update one inline child row |
| DELETE | `/{slug}/{pk}/inlines/{child_slug}/{child_pk}` | parent `.update` + child `.delete` | Delete one inline child row |

Plus one site-wide route: `GET {base_path}` renders the `Dashboard` if
one is configured, otherwise redirects to the first resource the
requester can view.

Every route runs the same authenticate → authorize sequence before
anything else — see [`authentication.md`](authentication.md) and
[`permissions.md`](permissions.md). A denied request never reaches the
`ModelAdmin` at all.

## HTMX partial routes

The list route detects `HX-Request: true` and, when present, renders
only the `#resource-list` fragment (table + pager + filters) instead
of the full page — this is what makes search/filter/sort/pagination
feel instant without a dedicated JSON API. Python's create/edit routes
do the same for form redisplay after a validation error
(`#resource-form`); the Go adapter mirrors this too
(`RenderFormFragment`, wired into both POST handlers).

## Inline routes

`ModelAdmin.inlines`' three generated routes (table above) don't follow
the list/form/detail routes' full-page-vs-fragment pattern — every
request against them, HTMX or not, is a **fragment** request: the
response body is always just the one inline section's freshly rebuilt
HTML (`<div id="inline-{child_slug}">...`), swapped into place via
`hx-target="#inline-{child_slug}"` `hx-swap="outerHTML"`, matching the
existing full-region-swap idiom `RenderListFragment`/
`render_list_fragment` and `RenderFormFragment`/`render_form_fragment`
already use elsewhere — never a redirect, never the whole parent page.

There's deliberately no `GET .../inlines/{child_slug}` route: the
section's initial content is already built as part of the parent's own
`GET /{slug}/{pk}` (detail) or `GET /{slug}/{pk}/edit` (edit) page, and
every mutating response already carries a fresh copy — no third moment
exists that would need its own fetch. See
[`inlines.md`](inlines.md) for the full feature.

## Custom admin pages

An application can register its own page — a report, a wizard, an
internal tool — alongside the generated CRUD routes, sharing the
admin's layout, authentication, and authorization. This is
`AdminPage`, registered via `Admin.route()`/`Admin.Route()`.

**Python:**

```python
async def contracts_report(ctx):
    return ctx.render("pages/contracts_report.html", rows=load_report())

admin.route(
    "/reports/contracts",
    contracts_report,
    label="Contracts Report",
    category="Reports",
)
```

The handler receives a `PageContext` (`polyadmin.fastapi.pages`) with:

- `.request` — the raw `fastapi.Request`, for query/path parsing.
- `await .form()` — shorthand for `await ctx.request.form()`.
- `.is_htmx` — whether the request came from an HTMX interaction.
- `.render(template_name, **extra)` — renders `template_name` inside
  the shared admin layout (sidebar, breadcrumbs, flash), the same
  three-level override resolution any other template gets. See
  [`templates.md`](templates.md).
- `.redirect(url, *, flash=(level, text))` — an HTMX-aware redirect
  that also sets a flash message, matching what every CRUD handler
  already does after a create/update/delete.

Handlers are async, matching every other FastAPI adapter handler.

**Go:**

```go
func contractsReportHandler(pc *fiberadapter.PageContext) error {
	return pc.Render("pages/contracts_report.html", loadReport())
}

admin.Route(
	"/reports/contracts",
	fiberadapter.PageHandler(contractsReportHandler),
	core.WithPageLabel("Contracts Report"),
	core.WithPageCategory("Reports"),
)
```

`AdminPage.Handler` is typed `any` in `core` (core must not import the
`fiber` adapter) — wrap your function in `fiberadapter.PageHandler(...)`
when registering it, the same explicit-wrap idiom as
`http.HandlerFunc`. `Mount` returns an `error` (not a panic) if a
page's `Handler` isn't actually a `fiberadapter.PageHandler`.
`PageContext` exposes:

- `.C` — the raw `*fiber.Ctx`, for query/form parsing.
- `.IsHTMX()` — whether the request came from an HTMX interaction.
- `.Render(templateName string, data any)` — renders `templateName`
  (must define a `{{define "content"}}` block, resolved from
  `WithTemplateDirs` — see [`templates.md`](templates.md)) inside the
  shared admin layout, with `data` handed to the template as `.Data`.
- `.Redirect(url)` / `.RedirectWithFlash(url, level, text)`.

**Both languages:** a page's HTTP methods default to `GET` and `POST`
— enough to render a form and repost to itself, the shape a
multi-step wizard needs — and can be narrowed with
`methods=(...)`/`core.WithPageMethods(...)`. Its permission defaults
to `"page.<path-with-dots>"` (`/reports/contracts` →
`"page.reports.contracts"`), checked the same way a resource route
checks `resource_permission`/`ResourcePermission` — see
[`permissions.md`](permissions.md#permission-names). Registering two
pages at the same path raises `ValueError`/panics, mirroring
`Admin.register`'s duplicate-slug behavior. Pages mount after all
`ModelAdmin` routes, in registration order.

By default a page gets a sidebar nav entry using its `label`; pass
`show_in_nav=False` (Python) / `core.WithPageHiddenFromNav()` (Go) to
register a route without one (e.g. a POST-only endpoint another page's
form submits to). See the next section for how `category` places it.

## Sidebar categories

Both a `ModelAdmin` and an `AdminPage` can declare a `category` —
items sharing one collapse into a single collapsible accordion section
in the sidebar, in first-registration-appearance order; items with no
category render as flat top-level links, unchanged from today.

```python
class UserAdmin(ModelAdmin):
    category = "Directory"
```

```go
BaseModelAdmin{NavCategory: "Directory"}
```

(Go names the field `NavCategory` — a `BaseModelAdmin` can't have a
field and a method both named `Category`, so it backs a `Category()`
method the same way `SlugOverride` backs `Slug()`.) A category's
accordion defaults to expanded if it contains the resource/page
currently being viewed, collapsed otherwise. There's no separate
Admin-level grouping config — a `ModelAdmin`/`AdminPage` owns its own
`category`, the same way it owns its own `slug`/`path`.

A category's accordion header always uses a fixed `folder` icon,
distinct from any resource's own icon — a category is just a string,
not an object with settings of its own, so there's nothing per-category
to configure. Each `ModelAdmin`/`AdminPage` has its own icon too
(`icon`/`NavIcon`, default `"collection"` — the icon every resource
link used before per-item icons existed), and keeps showing it whether
its link renders flat or nested inside a category's accordion:

```python
class UserAdmin(ModelAdmin):
    icon = "table"
```

```go
BaseModelAdmin{NavIcon: "table"}
```

See `templates/admin/components/icons.html` (Python) /
`fiber/icons.go`'s `iconPaths` (Go) for the available icon names.

The breadcrumb trail also reflects grouping: a `ModelAdmin`/`AdminPage`
with a `category` gets that category prepended as a plain (non-link,
non-bold) segment, right after the implicit home crumb — e.g.
Dashboard › Directory › Users. It's never a link, since a category
isn't a route by itself.
