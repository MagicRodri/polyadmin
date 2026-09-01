"""Audit logging: who changed what, and where the record of it lives.

Mirrors go-polyadmin/core/audit.go.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

AUDIT_CREATE = "create"
AUDIT_UPDATE = "update"
AUDIT_DELETE = "delete"


@dataclass
class AuditEntry:
    """One recorded change: who did what to which record.

    Deliberately flat and free of references into application state -- an
    entry outlives the request that made it, and a logger may serialise
    it, so it carries values rather than pointers to objects that may
    since have been deleted.
    """

    # When the change happened. Set by the framework, not the logger, so
    # entries from several processes agree on what "now" meant.
    at: datetime
    # One of AUDIT_CREATE/AUDIT_UPDATE/AUDIT_DELETE, or an Action's name
    # when a bulk or record action ran.
    action: str
    # The ModelAdmin's slug, and the affected record's primary key and
    # human label -- the label is captured at write time because the
    # record may not exist by the time anyone reads the log.
    resource: str
    object_pk: Any = None
    object_label: str = ""
    # Who made the change. None when no authenticator is configured,
    # which is also the case in which an audit log is least meaningful.
    principal: Any = None


@runtime_checkable
class AuditLogger(Protocol):
    """Receives an entry per change.

    The framework never stores entries itself: it does not own
    persistence any more than it owns identity (see
    docs/authentication.md), so where the log lives is the host
    application's decision.

    `record` is called after the change has succeeded. An error is
    reported, not swallowed, but never rolls the change back -- the
    record is already written, and failing the request would leave the
    user with an error next to a change that did happen.
    """

    def record(self, entry: AuditEntry) -> None:
        ...


@runtime_checkable
class AuditReader(Protocol):
    """The optional read side.

    A logger that implements this too gets a History section on the
    record's detail page; one that does not simply records without
    surfacing anything, which is a perfectly reasonable arrangement when
    the log's real consumer is elsewhere.

    Same optional-capability shape as list_page: implement more, get
    more, and nothing breaks if you do not.
    """

    def history(self, resource: str, pk: Any, limit: int) -> list[AuditEntry]:
        """The most recent entries for one record, newest first, capped
        at `limit`."""
        ...
