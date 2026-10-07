"""Recording changes into the configured audit logger."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from polyadmin.core.audit import AuditEntry
from polyadmin.core.model_admin import ModelAdmin

logger = logging.getLogger("polyadmin")


def object_label(model_admin: ModelAdmin, obj: Any) -> str:
    """A short human label for an object, matching the breadcrumb rule:
    the first search field, else the first list column, else the pk.
    """
    names = list(model_admin.search_fields) or list(model_admin.list_display)
    for name in names:
        try:
            return str(model_admin.get_field(name).get_value(obj))
        except KeyError:
            continue
    return str(model_admin.get_pk(obj))


def record_audit(admin: Any, principal: Any, model_admin: ModelAdmin, action: str, obj: Any) -> None:
    """Write one entry, if a logger is configured at all.

    Called after the change has already succeeded, so a logger error is
    reported and dropped rather than raised: failing the request here
    would show the user an error beside a change that did happen, which
    is worse than a missing log line. The label is captured now because
    the record may be gone by the time anyone reads the entry.
    """
    if admin.audit_logger is None:
        return
    entry = AuditEntry(
        at=datetime.now(timezone.utc),
        principal=principal,
        action=action,
        resource=model_admin.get_slug(),
        object_pk=model_admin.get_pk(obj) if obj is not None else None,
        object_label=object_label(model_admin, obj) if obj is not None else "",
    )
    try:
        admin.audit_logger.record(entry)
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        logger.warning(
            "audit log rejected a %s on %s: %s", action, model_admin.get_slug(), exc
        )
