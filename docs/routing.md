# Routing

How an `Admin` becomes actual HTTP routes, and what routes get
generated per `ModelAdmin`.

## Mounting

An `APIRouter` you include yourself:

```python
from fastapi import FastAPI
from polyadmin.fastapi.router import create_router

app = FastAPI()
app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
```

`base_path` must match the `prefix` passed to `include_router` — it's
used to build every link the templates render (nav, pagination,
redirects, the relation lookup URL) and isn't derived from the router
automatically, since the router is built before FastAPI knows where it
will be mounted.

## Generated routes

For each registered `ModelAdmin`, gated by its own
`can_view`/`can_create`/`can_update`/`can_delete`/`can_export` flags:

| Method | Path | Requires | Purpose |
|---|---|---|---|
| GET | `/{slug}` | `.view` | List (search/filter/sort/paginate) |
| GET, POST | `/{slug}/create` | `.create` | Create form |
| GET | `/{slug}/{pk}` | `.view` | Detail |
| GET, POST | `/{slug}/{pk}/edit` | `.update` | Edit form |
| GET, POST, DELETE | `/{slug}/{pk}/delete` | `.delete` | Delete confirmation / non-HTMX delete / HTMX inline delete |
| GET | `/{slug}/lookup` | `.view` | Relation-autocomplete search fragment |
| POST | `/{slug}/actions/{name}` | `.view` (+ the action's own `permission`, if set) | Run a record/bulk Action — only registered if the `ModelAdmin` declares any |
| GET | `/{slug}/export/{format}` | `.export` | Streamed export — `csv` and `xlsx` |
| POST | `/{slug}/{pk}/inlines/{child_slug}` | parent `.update` + child `.create` | Create one inline child row — only registered if the `ModelAdmin` declares any `inlines` |
| POST | `/{slug}/{pk}/inlines/{child_slug}/{child_pk}` | parent `.update` + child `.update` | Update one inline child row |
| DELETE | `/{slug}/{pk}/inlines/{child_slug}/{child_pk}` | parent `.update` + child `.delete` | Delete one inline child row |

Plus one site-wide route: `GET {base_path}` renders the `Dashboard` if
one is configured, otherwise redirects to the first resource the
requester can view.

And, **only when a `login_backend` is configured** (see
[`authentication.md`](authentication.md#the-login-page)), three more:

| Method | Path | Requires | Purpose |
|---|---|---|---|
| GET | `/login` | — | The login page |
| POST | `/login` | — | Verify credentials, begin the session |
| POST | `/logout` | — | End the session |

These are the only routes in a mounted admin that do not authenticate:
requiring a session to reach the page that creates one is a loop. They
are still CSRF-protected. They mount before the `ModelAdmin` routes, so
a resource whose slug is `login` collides visibly rather than silently
shadowing the login page.

Every route above runs the same authenticate → authorize sequence
before anything else — see [`authentication.md`](authentication.md) and
[`permissions.md`](permissions.md). A denied request never reaches the
`ModelAdmin` at all.

## HTMX partial routes

The list route detects `HX-Request: true` and, when present, renders
only the `#resource-list` fragment (table + pager + filters) instead
of the full page — this is what makes search/filter/sort/pagination
feel instant without a dedicated JSON API. The create/edit routes do
the same for form redisplay after a validation error (`#resource-form`,
via `render_form_fragment`, wired into both POST handlers).

## Inline routes

`ModelAdmin.inlines`' three generated routes (table above) don't follow
the list/form/detail routes' full-page-vs-fragment pattern — every
request against them, HTMX or not, is a **fragment** request: the
response body is always just the one inline section's freshly rebuilt
HTML (`<div id="inline-{child_slug}">...`), swapped into place via
`hx-target="#inline-{child_slug}"` `hx-swap="outerHTML"`, matching the
existing full-region-swap idiom `render_list_fragment` and
`render_form_fragment` already use elsewhere — never a redirect, never
the whole parent page.

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
`AdminPage`, registered via `Admin.route()`.

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

A page's HTTP methods default to `GET` and `POST` — enough to render a
form and repost to itself, the shape a multi-step wizard needs — and
can be narrowed with `methods=(...)`. Its permission defaults to
`"page.<path-with-dots>"` (`/reports/contracts` →
`"page.reports.contracts"`), checked the same way a resource route
checks `resource_permission` — see
[`permissions.md`](permissions.md#permission-names). Registering two
pages at the same path raises `ValueError`, mirroring
`Admin.register`'s duplicate-slug behavior. Pages mount after all
`ModelAdmin` routes, in registration order.

By default a page gets a sidebar nav entry using its `label`; pass
`show_in_nav=False` to register a route without one (e.g. a POST-only
endpoint another page's form submits to). See the next section for how
`category` places it.

## Sidebar categories

Both a `ModelAdmin` and an `AdminPage` can declare a `category` —
items sharing one collapse into a single collapsible accordion section
in the sidebar, in first-registration-appearance order; items with no
category render as flat top-level links.

```python
class UserAdmin(ModelAdmin):
    category = "Directory"
```

A category's accordion defaults to expanded if it contains the
resource/page currently being viewed, collapsed otherwise. There's no
separate Admin-level grouping config — a `ModelAdmin`/`AdminPage` owns
its own `category`, the same way it owns its own `slug`/`path`.

A category's accordion header always uses a fixed `folder` icon,
distinct from any resource's own icon — a category is just a string,
not an object with settings of its own, so there's nothing per-category
to configure. Each `ModelAdmin`/`AdminPage` has its own icon too
(`icon`, default `"collection"`), and keeps showing it whether its link
renders flat or nested inside a category's accordion:

```python
class UserAdmin(ModelAdmin):
    icon = "table"
```

See `templates/admin/components/icons.html` for the available icon
names.

The breadcrumb trail also reflects grouping: a `ModelAdmin`/`AdminPage`
with a `category` gets that category prepended as a plain (non-link,
non-bold) segment, right after the implicit home crumb — e.g.
Dashboard › Directory › Users. It's never a link, since a category
isn't a route by itself.
