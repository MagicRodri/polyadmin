# examples/fastapi

Reference FastAPI application exercising `python/polyadmin`: `User`
and `Organization` models (a foreign key relation), with CRUD, search,
filters, a dashboard, authentication/authorization, actions, and
CSV/XLSX export.

Run it:

```bash
uv sync
uv run uvicorn main:app --reload
# open http://127.0.0.1:8000/admin
```

Run its tests:

```bash
uv run pytest
```
