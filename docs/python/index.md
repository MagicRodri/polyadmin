# Python

The Python implementation provides the core admin experience for Python
applications. The current web adapter mounts PolyAdmin into FastAPI.

## Install from PyPI

PolyAdmin is published on PyPI. Install the FastAPI adapter with:

```bash
pip install "polyadmin[fastapi]"
```

## First steps

1. Define a `ModelAdmin` for each resource.
2. Register the model admins with `Admin`.
3. Create a router with `create_router`.
4. Mount that router in FastAPI.

Then continue with the [Python ModelAdmin guide](../model-admin.md) and the
[Python architecture guide](../architecture.md).