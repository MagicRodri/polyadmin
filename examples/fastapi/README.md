# examples/fastapi

Reference FastAPI application exercising PolyAdmin: `User`,
`Organization` and `Role` models with foreign-key and many-to-many
relations, inlines, a dashboard, search/filter/sort, actions, a custom
Tools page, CSV/XLSX export, and a real login.

Run it:

```bash
uv sync
uv run uvicorn main:app --reload
# open http://127.0.0.1:8000/admin
```

## Signing in

The admin is behind a real login (`session.py`), not a hardcoded
superuser. Two accounts, both with the password `polyadmin`:

| Email | | Can |
|---|---|---|
| `admin@example.com` | superuser | everything |
| `viewer@example.com` | not a superuser | read and export; no create/update/delete, no Tools page |

Two accounts, so the permission system is visible rather than theoretical.
Signed in as the viewer, the list's **Add** button and the per-row
edit/delete controls are simply absent — `compute_permissions` asks the
`Authorizer` which controls to render — and a hand-made `POST` to
`/admin/users/create` still gets `403`, because the routes enforce this
independently of what the templates chose to show.

The rule lives in `ReadOnlyForNonSuperusers` (`session.py`), not
`SuperuserAuthorizer`: that one is all-or-nothing, so a non-superuser
would be refused *every* permission including `dashboard.view` and would
meet a bare "Permission denied." on every page.

Sessions are HMAC-signed cookies keyed by `ADMIN_SESSION_SECRET`. If
that variable is unset a random per-process secret is generated, so
sessions end when the process does; set it to keep them across
restarts:

```bash
ADMIN_SESSION_SECRET=$(openssl rand -hex 32) uv run uvicorn main:app
```

`session.py` is meant to be copied and adapted — swap the in-memory
account table for your own user store. See
[`../../docs/authentication.md`](../../docs/authentication.md#the-login-page).

Run its tests:

```bash
uv run pytest
```
