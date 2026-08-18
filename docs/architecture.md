# Architecture

PolyAdmin is one design, implemented twice, in two separate
repositories: [MagicRodri/polyadmin](https://github.com/MagicRodri/polyadmin)
for FastAPI and [MagicRodri/go-polyadmin](https://github.com/MagicRodri/go-polyadmin)
for Fiber. Neither depends on the other or shares runtime code — the guarantee is that the same concepts, named
the same way, produce the same routes and the same UI in both
languages. This document explains how the pieces fit together; for
any one concept in depth, see the other files in this directory.

## The four core objects

**`Field`** describes one model attribute's admin presentation: its
type (string, integer, boolean, date, email, foreign key, ...),
whether it's required/readonly/disabled, and how to read a value off
an arbitrary object and coerce a submitted form value back into one.
Fields don't know about HTTP or HTML — they're the data-level contract
everything else builds on. See [`model-admin.md`](model-admin.md).

**`ModelAdmin`** is one resource: which model it administers, which
fields appear in the list/detail/form views, search/filter/ordering
config, the CRUD lifecycle hooks (`get_queryset`/`GetQueryset`,
`get_object`/`GetObject`, `create`/`Create`, `update`/`Update`,
`delete`/`Delete`), and optional Actions and autocomplete relation
fields. A `ModelAdmin` never touches your database directly — it's an
abstract contract; your subclass implements the lifecycle hooks
against whatever storage you actually have. See
[`model-admin.md`](model-admin.md).

**`Admin`** is the site: a registry of `ModelAdmin`s keyed by slug,
plus the optional `Dashboard`, `Authenticator`, and `Authorizer` for
the whole site, and branding (`site_title`/`SiteTitle`,
`site_logo_url`/`SiteLogoURL`). It owns no HTTP concerns either —
mounting it onto a real router is the adapter's job.

**The adapter** (`polyadmin.fastapi` / `polyadmin/fiber`) is the only
layer that knows about HTTP. `create_router(admin, base_path=...)` /
`Mount(router, admin, basePath)` walks the `Admin`'s registry and
builds routes for each viewable/creatable/updatable/deletable/
exportable `ModelAdmin`, wires in the `Authenticator`/`Authorizer` on
every route, and renders responses through a `Renderer`. See
[`routing.md`](routing.md).

## Request flow

A request for `GET /admin/users` (list view) goes:

1. The adapter's route handler authenticates the request
   (`Authenticator.authenticate` → a `Principal` or `None`) and
   authorizes it (`Authorizer.can(principal, "users.list", model_admin)`)
   before anything else runs.
2. `ModelAdmin.get_queryset()`/`GetQueryset()` returns the resource's
   base collection.
3. The shared query pipeline (`core/query.py` / `core/query.go`)
   applies search, declared `Filter`s, and ordering from the query
   string; `Paginator`/`Paginate` slices the result.
4. Per-row/detail relation fields are resolved against the
   `Authorizer` too — a relation only renders as a clickable link if
   the principal can view the target resource, otherwise it falls back
   to plain text.
5. The `Renderer` picks a template (see [`templates.md`](templates.md)
   for the override order), builds its context, and returns HTML — a
   full page normally, or just the `#resource-list` fragment when the
   request came from an HTMX-driven search/filter/sort/pagination
   interaction.

Every other route (detail, create, edit, delete, lookup, actions,
export) follows the same authenticate → authorize → do the thing →
render shape.

## Why two independent implementations

The API in each language is idiomatic to that language rather than a
literal port: Python uses class attributes and keyword arguments
(`class UserAdmin(ModelAdmin): list_display = (...)`); Go uses
functional options and struct embedding (`core.NewField(...,
core.WithRequired())`, `BaseModelAdmin` embedded and its methods
promoted). Field/form HTML is built inside `.html` template files in
Python (Jinja2 autoescaping) but in plain Go functions in
`render_helpers.go` on the Go side, for tighter control over escaping
with `html/template`. The contract each implements — routes, template
context shape, HTML output — is kept in lockstep by mirroring tests
across both suites, not by sharing code.

## Frontend

Both languages render server-side HTML styled with
[PinesUI](https://devdojo.com/pines) conventions (Tailwind's neutral
palette, Alpine.js for interactivity, no separate JS component
framework) and use HTMX for partial-page updates (list search/filter/
sort/pagination, and form validation redisplay). Tailwind, Alpine, and
HTMX are all CDN-loaded — neither implementation has a frontend build
step.
