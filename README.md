# PolyAdmin (Python)

Python implementation of PolyAdmin, the cross-language server-rendered
admin framework. See [`docs/`](docs/) for reference documentation.

The Go/Fiber implementation is a separate repository:
[MagicRodri/go-polyadmin](https://github.com/MagicRodri/go-polyadmin).
The two share no runtime code — they're the same design implemented
twice, at feature parity. The `docs/` here cover both, so most pages
show Python and Go side by side.

## What you get from declaring a `ModelAdmin`

Point one at your model (fields, `list_display`, search/filter config,
permissions) and you get:

- Full CRUD with search, filter, sort, and pagination, all swapped in
  via HTMX partials — no full-page reloads
- A dashboard of pluggable widgets: metric, stat (value + trend),
  progress bar, bar chart, donut/pie breakdown, table, activity feed,
  timeline, and tabs (several widgets in one card)
- Sidebar grouping — resources sharing a `category` collapse into one
  collapsible accordion section, e.g. everything CRUD-shaped under
  one "Directory" group
- Custom admin pages (`admin.route`) for functionality that isn't
  resource CRUD — reports, wizards, internal tools — rendered inside
  the same layout, auth, and sidebar grouping as everything else
- Relation fields rendered as links, or as a searchable shadcn/ui
  Command-style autocomplete backed by a server-side `/lookup` route
  (never dumps the target model's full queryset into the page)
- Inline related records (`StackedInline`/`TabularInline`) — a
  parent's create/detail/edit pages can show and manage a child's
  records that point back at it, Django-admin style
- Record and bulk Actions, with a shadcn/ui Dialog confirmation step for
  destructive ones
- Authentication/authorization hooks gating every route *and* every
  control the templates render
- CSV and XLSX export
- Toast notifications for every create/update/delete/action
- Per-resource (and per-widget) template overrides, so an application
  can replace one view's markup without forking the framework

Styling is [shadcn/ui](https://ui.shadcn.com), hand-ported to
Alpine.js + Tailwind — its CSS-variable token system and component
markup, without React or Radix. That gives the admin **dark mode and
themability**: every color resolves through a CSS variable, so restyling
the whole thing is a change to one template. The layout is mobile-first
with a collapsible sidebar (a Sheet below `md`), a Django-admin-style
right-hand filter panel on wider screens, and breadcrumbs as the page
title. Tailwind/Alpine/HTMX are all CDN-loaded — no frontend build step.
See [`docs/components.md`](docs/components.md).

## Quickstart

Not yet published to PyPI — install from git:

```toml
# pyproject.toml
[project]
dependencies = ["polyadmin"]

[tool.uv.sources]
polyadmin = { git = "https://github.com/MagicRodri/polyadmin.git" }
```

Declare a `ModelAdmin` against your own storage and mount it on a
FastAPI app:

```python
from dataclasses import dataclass

from fastapi import FastAPI
from polyadmin import BooleanField, EmailField, ModelAdmin
from polyadmin.core.admin import Admin
from polyadmin.fastapi.router import create_router


@dataclass
class User:
    id: int
    email: str
    is_active: bool = True


_users: list[User] = []


class UserAdmin(ModelAdmin):
    model = User
    list_display = ("id", "email", "is_active")
    form_fields = ("email", "is_active")
    search_fields = ("email",)
    fields = (
        EmailField("email", required=True),
        BooleanField("is_active", default=True),
    )

    def get_queryset(self):
        return _users

    def get_object(self, pk):
        return next((u for u in _users if u.id == int(pk)), None)

    def create(self, data):
        user = User(id=len(_users) + 1, **data)
        _users.append(user)
        return user

    def update(self, obj, data):
        obj.email = data["email"]
        obj.is_active = data["is_active"]
        return obj

    def delete(self, obj):
        _users.remove(obj)


admin = Admin(model_admins=[UserAdmin()])

app = FastAPI()
app.include_router(create_router(admin, base_path="/admin"), prefix="/admin")
```

```bash
uv run uvicorn main:app --reload
# open http://127.0.0.1:8000/admin
```

That's a full CRUD admin for `User` — search, sort, create, edit,
delete, CSV/XLSX export, all with zero routes or templates of your
own. With no `authenticator`/`authorizer` set, every request is
allowed by default (fine for exploring locally, not for anything
real) — see [`docs/authentication.md`](docs/authentication.md)
and [`docs/permissions.md`](docs/permissions.md) before
deploying. For everything else a `ModelAdmin` supports (relations,
filters, actions, a dashboard, exports), see
[`docs/model-admin.md`](docs/model-admin.md); for the UI components and
theming, [`docs/components.md`](docs/components.md); and for the rest,
[`docs/`](docs/).

## Status

All 9 implementation phases are done:

- **Core** (`polyadmin/core/`): `Admin`, `ModelAdmin`, `Field` (incl. relation
  field types), `Relation`, `Filter`, the list query pipeline (`query.py`),
  `Paginator`, `Authenticator`/`Principal`, `Authorizer`, `Dashboard`/`Widget`,
  `Exporter` (CSV + XLSX).
- **Rendering** (`polyadmin/templating.py`, `polyadmin/templates/`): Jinja2
  templates with framework/app/resource override resolution and
  `TemplateContext` builders. Tailwind/Alpine/HTMX are CDN-loaded
  — no frontend build step required.
- **FastAPI adapter** (`polyadmin/fastapi/`): `create_router` mounts full CRUD +
  list/detail/create/edit/delete + relation lookup + CSV/XLSX export routes,
  with HTMX partial-swap for list search/filter/sort/pagination and for
  forms, flash messages surviving a redirect, and auth/permission
  enforcement on every route (also gates which controls the templates show).

See [`examples/fastapi`](examples/fastapi) for a full runnable
reference app exercising all of this.

## Development

```bash
uv sync
uv run pytest   # 205 tests
```
