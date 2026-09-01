# Architecture

PolyAdmin is a Django-admin-style admin framework for
[FastAPI](https://fastapi.tiangolo.com). It owns presentation —
routes, forms, tables, permissions checks, HTML — and owns no storage:
your `ModelAdmin` implements the lifecycle hooks against whatever
database or service you already have. This document explains how the
pieces fit together; for any one concept in depth, see the other files
in this directory.

## The four core objects

**`Field`** describes one model attribute's admin presentation: its
type (string, integer, boolean, date, email, foreign key, ...),
whether it's required/readonly/disabled, and how to read a value off
an arbitrary object and coerce a submitted form value back into one.
Fields don't know about HTTP or HTML — they're the data-level contract
everything else builds on. See [`model-admin.md`](model-admin.md).

**`ModelAdmin`** is one resource: which model it administers, which
fields appear in the list/detail/form views, search/filter/ordering
config, the CRUD lifecycle hooks (`get_queryset`, `get_object`,
`create`, `update`, `delete`), and optional Actions and autocomplete
relation fields. A `ModelAdmin` never touches your database directly —
it's an abstract contract; your subclass implements the lifecycle hooks
against whatever storage you actually have. See
[`model-admin.md`](model-admin.md).

**`Admin`** is the site: a registry of `ModelAdmin`s keyed by slug,
plus the optional `Dashboard`, `Authenticator`, and `Authorizer` for
the whole site, and branding (`site_title`, `site_logo_url`). It owns
no HTTP concerns either — mounting it onto a real router is the
adapter's job.

**The adapter** (`polyadmin.fastapi`) is the only layer that knows
about HTTP. `create_router(admin, base_path=...)` walks the `Admin`'s
registry and builds routes for each
viewable/creatable/updatable/deletable/exportable `ModelAdmin`, wires
in the `Authenticator`/`Authorizer` on every route, and renders
responses through a `Renderer`. See [`routing.md`](routing.md).

## Request flow

A request for `GET /admin/users` (list view) goes:

1. The adapter's route handler authenticates the request
   (`Authenticator.authenticate` → a `Principal` or `None`) and
   authorizes it (`Authorizer.can(principal, "users.list", model_admin)`)
   before anything else runs.
2. `ModelAdmin.get_queryset()` returns the resource's base collection —
   or, if the `ModelAdmin` defines `list_page`, that resolves search,
   filters, ordering and the page window in one go against the data
   source itself.
3. The query pipeline (`core/query.py`) applies search, declared
   `Filter`s, and ordering from the query string; `paginate` slices the
   result.
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

## An idiomatic Python API

The API is declarative in the way Django's admin is: a `ModelAdmin`
subclass configured with class attributes (`list_display`,
`search_fields`, `fieldsets`), fields built with keyword arguments
(`StringField("email", required=True)`), and lifecycle hooks you
override only when the default won't do.

Optional capabilities are duck-typed rather than forced onto every
subclass: a `ModelAdmin` that defines `list_page` gets database-side
pagination, one that doesn't keeps working through `get_queryset`. The
same shape gives an audit logger an optional read side (`AuditReader`)
and an application an optional login page (`LoginBackend`) — each a
`Protocol` the framework checks for, never a method you must stub out.

Field and form HTML is built inside the `.html` template files, where
Jinja2's autoescaping applies.

## Frontend

The admin renders server-side HTML styled with
[shadcn/ui](https://ui.shadcn.com), hand-ported to Alpine.js + Tailwind:
its CSS-variable token system and component markup, with Radix's
behavior reimplemented in Alpine and no React anywhere. Colors resolve
through those variables rather than a literal palette, which is what
makes the admin themeable and dark-mode-capable. HTMX handles
partial-page updates (list search/filter/sort/pagination, and form
validation redisplay). Tailwind, Alpine (plus its focus/collapse/anchor
plugins), and HTMX are all CDN-loaded — there is no frontend build
step.

See [`components.md`](components.md) for the component reference and the
porting rationale, and [`templates.md`](templates.md#styling) for how to
retheme.
