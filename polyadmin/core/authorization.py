"""Authorizer: can(principal, permission, resource).

Standard permission names: `dashboard.view` and, per resource,
`{slug}.list` / `.view` / `.create` / `.update` / `.delete` / `.export`,
built by `resource_permission`. Applications add action-specific
permission strings of their own alongside these.

Authorization is always enforced server-side by the adapter --
`resource_permission` results also flow into templates so they can
hide controls the current principal can't use, but that's a UX
nicety, never the security boundary itself.
"""
from __future__ import annotations

from typing import Any, Protocol

DASHBOARD_VIEW = "dashboard.view"


def resource_permission(slug: str, action: str) -> str:
    return f"{slug}.{action}"


class Authorizer(Protocol):
    def can(self, principal: Any, permission: str, resource: Any = None) -> bool: ...


class AllowAllAuthorizer:
    """Grants every permission. For local development and tests only."""

    def can(self, principal: Any, permission: str, resource: Any = None) -> bool:
        return True


class DenyAllAuthorizer:
    """Denies every permission. Useful for asserting a gate works."""

    def can(self, principal: Any, permission: str, resource: Any = None) -> bool:
        return False


class SuperuserAuthorizer:
    """Grants every permission to superusers, denies everyone else -- a
    reasonable default before an application builds out granular roles.
    """

    def can(self, principal: Any, permission: str, resource: Any = None) -> bool:
        return bool(getattr(principal, "is_superuser", False))
