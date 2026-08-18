"""Authenticator: Request -> Principal.

The admin doesn't care whether authentication comes from session
cookies, JWT, OAuth, or an existing IAM service -- only that something
can turn an inbound request into a Principal, or None if unauthenticated.
`request` is intentionally untyped here: whatever object the adapter
(e.g. a FastAPI Request) passes through is opaque to core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Principal:
    id: Any
    display_name: str = ""
    is_superuser: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class Authenticator(Protocol):
    def authenticate(self, request: Any) -> Principal | None: ...


class AllowAllAuthenticator:
    """Authenticates every request as the same Principal.

    For local development and tests only -- never wire this into a
    real deployment.
    """

    def __init__(self, principal: Principal | None = None) -> None:
        self._principal = principal or Principal(id="anonymous", display_name="Anonymous", is_superuser=True)

    def authenticate(self, request: Any) -> Principal | None:
        return self._principal


class DenyAllAuthenticator:
    """Authenticates nobody. Useful for asserting a login gate works."""

    def authenticate(self, request: Any) -> Principal | None:
        return None
