"""Bridges a hook that may return a value or an awaitable.

The CRUD lifecycle (`get_queryset`, `get_object`, `create`, `update`,
`delete`, `list_page`) and `Authenticator.authenticate` may each be a plain
function or an `async def` -- a ModelAdmin backed by an async HTTP client
needs the latter. `maybe_await` lets one call site handle both without the
author declaring which upfront.
"""
from __future__ import annotations

import inspect
from typing import Awaitable, TypeVar

T = TypeVar("T")


async def maybe_await(value: "T | Awaitable[T]") -> "T":
    if inspect.isawaitable(value):
        return await value
    return value
