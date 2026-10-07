"""What a principal may do with a resource, for the templates to decide which
controls to show. Framework-neutral: it only asks the Admin's authorizer."""

from __future__ import annotations

from typing import Any

from polyadmin.core.admin import Admin
from polyadmin.core.authorization import resource_permission
from polyadmin.core.model_admin import ModelAdmin


def compute_permissions(
    admin: Admin, principal: Any, model_admin: ModelAdmin, obj: Any = None
) -> dict[str, bool]:
    """What the principal may do with this resource, combining the ModelAdmin's
    static can_* toggles with the Authorizer's per-request decision. It decides
    which controls the templates show; the routes enforce this independently,
    so hiding a control is a UX nicety, not the security boundary.
    """
    slug = model_admin.get_slug()

    def allowed(capability: bool, action: str) -> bool:
        if not capability:
            return False
        if admin.authorizer is None:
            return True
        # obj is the record in view, or None on a list or create page.
        # When present it is what the authorizer is asked about, so per-
        # object rules decide which controls that record's pages show.
        resource = model_admin if obj is None else obj
        return admin.authorizer.can(principal, resource_permission(slug, action), resource)

    # Keys are "can_view" etc -- see default_permissions in
    # template_context.py for why "update" alone is unsafe here.
    return {
        "can_view": allowed(model_admin.can_view, "view"),
        "can_create": allowed(model_admin.can_create, "create"),
        "can_update": allowed(model_admin.can_update, "update"),
        "can_delete": allowed(model_admin.can_delete, "delete"),
        "can_export": allowed(model_admin.can_export, "export"),
    }
