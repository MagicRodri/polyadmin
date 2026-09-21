# Shared architecture

The Python and Go implementations follow the same four-layer model:

1. **Application** owns models, storage, business logic, and authentication.
2. **Model admin** describes one resource and its CRUD capabilities.
3. **Admin site** registers resources and configures dashboard, branding, and
   authorization.
4. **Web adapter** mounts the site into the host framework and handles HTTP.

The framework owns presentation but does not assume a database or ORM. A
resource implementation supplies the lifecycle operations needed by its
language adapter. This keeps the admin useful with in-memory data, SQL,
document stores, or service APIs.

The request lifecycle is intentionally consistent across both libraries:

```text
request
  -> authenticate
  -> authorize
  -> resolve resource and query
  -> render full page or HTMX fragment
```

See the [Python architecture](../architecture.md) or
[Go architecture](../go/reference/architecture.md) pages for the language-
level interfaces and naming conventions.