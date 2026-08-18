# PolyAdmin (Python)

Python implementation of PolyAdmin, the cross-language server-rendered
admin framework. See [`docs/`](docs/) for reference documentation.

The Go/Fiber implementation is a separate repository:
[MagicRodri/go-polyadmin](https://github.com/MagicRodri/go-polyadmin).
The two share no runtime code — they're the same design implemented
twice, at feature parity. The `docs/` here cover both, so most pages
show Python and Go side by side.

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
[`docs/model-admin.md`](docs/model-admin.md) and the rest of
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
