# Python / FastAPI

The Python implementation mounts PolyAdmin into a FastAPI application.

## Install from Git

PolyAdmin is not yet published to PyPI. Add it as a Git dependency using the
instructions in the [Python README](https://github.com/MagicRodri/polyadmin/blob/main/README.md).

## First steps

1. Define a `ModelAdmin` for each resource.
2. Register the model admins with `Admin`.
3. Create a router with `create_router`.
4. Mount that router in FastAPI.

Then continue with the [Python ModelAdmin guide](../model-admin.md) and the
[Python architecture guide](../architecture.md).