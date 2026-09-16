"""Delete previews (docs/deletes.md): an optional ModelAdmin capability that
says what else a delete takes out and what forbids it, and the resolution
that makes a host's answer safe to show one principal.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from polyadmin.core.authorization import resource_permission

# How many records of a group are listed; the rest are counted.
DELETE_PREVIEW_SAMPLE = 10


@dataclass(frozen=True)
class DeleteGroup:
    """One related type's share of a preview. `resource` is a registered slug,
    or "" for a type the admin does not manage (then `label` is required).
    `label` is a host string translated at render; "" falls back to the
    resource's verbose name. `objects` is a sample; `total` the full count,
    raised to len(objects) when smaller.
    """

    resource: str = ""
    label: str = ""
    objects: Sequence[Any] = ()
    total: int = 0


@dataclass(frozen=True)
class DeletePreview:
    cascades: Sequence[DeleteGroup] = ()  # deleted along with the objects
    protected: Sequence[DeleteGroup] = ()  # prevent the delete while they exist


class DeletePreviewer(Protocol):
    """An optional ModelAdmin capability: implement `delete_preview` to show
    what else a delete takes out, and to block deletes your storage would
    refuse. Same optional-capability shape as ListQuerier: implement more,
    get more, and nothing breaks if you do not.

    `objects` is always a list -- one record from the delete page, the whole
    selection from delete_selected -- so an implementation over SQL can
    answer a bulk delete with one count and one sample query per relation.
    """

    def delete_preview(self, objects: list[Any]) -> DeletePreview: ...


@dataclass
class ResolvedDeleteGroup:
    label: str  # untranslated
    total: int
    model_admin: Any = None  # None for a type the admin does not manage
    visible: list[Any] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    hidden: int = 0
    more: int = 0


@dataclass
class ResolvedDeletePreview:
    cascades: list[ResolvedDeleteGroup] = field(default_factory=list)
    protected: list[ResolvedDeleteGroup] = field(default_factory=list)
    denied_types: list[str] = field(default_factory=list)  # untranslated labels
    blocked: bool = False


def previews_deletes(model_admin: Any) -> bool:
    return callable(getattr(model_admin, "delete_preview", None))


def resolve_delete_preview(admin: Any, model_admin: Any, principal: Any, objects: Sequence[Any]) -> ResolvedDeletePreview:
    """Ask model_admin what deleting objects takes with it and filter the answer
    for principal. Without the capability: an empty, non-blocking result, and
    nothing is called.
    """
    if not previews_deletes(model_admin):
        return ResolvedDeletePreview()
    preview = model_admin.delete_preview(list(objects))
    out = ResolvedDeletePreview()
    for group in preview.cascades:
        resolved = _resolve_group(admin, principal, group)
        if resolved is None:
            continue
        out.cascades.append(resolved)
        target = resolved.model_admin
        if target is not None and not _allows(
            admin, principal, target.can_delete, resource_permission(target.get_slug(), "delete"), target
        ):
            out.denied_types.append(resolved.label)
    for group in preview.protected:
        resolved = _resolve_group(admin, principal, group)
        if resolved is not None:
            out.protected.append(resolved)
    out.blocked = bool(out.protected or out.denied_types)
    return out


def _resolve_group(admin: Any, principal: Any, group: DeleteGroup) -> ResolvedDeleteGroup | None:
    total = max(group.total, len(group.objects))
    if total == 0:
        return None
    sample = list(group.objects)[:DELETE_PREVIEW_SAMPLE]
    resolved = ResolvedDeleteGroup(label=group.label, total=total, more=total - len(sample))
    if not group.resource:
        if not group.label:
            raise ValueError("A DeleteGroup needs a resource or a label.")
        resolved.texts = [str(obj) for obj in sample]
        return resolved
    try:
        target = admin.get_model_admin(group.resource)
    except KeyError:
        raise ValueError(f"delete_preview names unregistered resource {group.resource!r}.") from None
    resolved.model_admin = target
    resolved.label = resolved.label or target.get_verbose_name()
    # The detail page's two checks: the coarse one against the resource, then
    # the per-object one. A record failing either is counted, never named.
    permission = resource_permission(target.get_slug(), "view")
    viewable = _allows(admin, principal, target.can_view, permission, target)
    for obj in sample:
        if viewable and _allows(admin, principal, True, permission, obj):
            resolved.visible.append(obj)
        else:
            resolved.hidden += 1
    return resolved


def _allows(admin: Any, principal: Any, capability: bool, permission: str, resource: Any) -> bool:
    """compute_permissions' rule for one check: the static toggle, then the
    Authorizer if there is one."""
    if not capability:
        return False
    return admin.authorizer is None or admin.authorizer.can(principal, permission, resource)


def selection_fingerprint(model_admin: Any, objects: Sequence[Any]) -> str:
    """The hex SHA-256 of the records' primary keys, sorted and newline-joined.
    The delete_selected confirmation carries it so "all N matching" deletes
    exactly the set that was reviewed."""
    pks = sorted(str(model_admin.get_pk(obj)) for obj in objects)
    return hashlib.sha256("\n".join(pks).encode()).hexdigest()
