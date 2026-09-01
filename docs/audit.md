# Audit logging

The admin can record every change it makes — who did what, to which
record, and when. **Where that record lives is your decision**: the
framework does not store a log itself, for the same reason it does not
own identity or persistence (see [`authentication.md`](authentication.md)).

Nothing is recorded until you configure a logger.

## Recording

Implement one method and hand it to the admin:

```go
type auditToDB struct{ db *sql.DB }

func (a auditToDB) Record(ctx context.Context, e core.AuditEntry) error {
    _, err := a.db.ExecContext(ctx,
        `INSERT INTO admin_log (at, who, action, resource, pk, label) VALUES ($1,$2,$3,$4,$5,$6)`,
        e.At, principalID(e.Principal), e.Action, e.Resource, e.ObjectPK, e.ObjectLabel)
    return err
}

admin := core.New(core.WithModelAdmins(...), core.WithAuditLogger(auditToDB{db}))
```
```python
class AuditToDB:
    def record(self, entry):
        db.execute(
            "INSERT INTO admin_log (at, who, action, resource, pk, label)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (entry.at, principal_id(entry.principal), entry.action,
             entry.resource, entry.object_pk, entry.object_label),
        )

admin = Admin(model_admins=[...], audit_logger=AuditToDB())
```

An entry is written for every **create**, **update** and **delete**, and
for every record a bulk or record **action** touched — one entry per
record, not one per action run, because the log's question is "what
happened to this record".

Two deliberate properties:

- **Entries follow a successful change.** A rejected save records
  nothing.
- **A logger error never fails the request.** The change already
  happened; showing the user an error beside it would be a lie. The
  error is logged and dropped.

`ObjectLabel`/`object_label` is captured at write time rather than
resolved on read, because the record may not exist by the time anyone
reads the entry — which is precisely the case for a delete.

## Showing history

If your logger *also* implements the read side, each record's detail
page grows a **History** panel listing recent activity:

```go
func (a auditToDB) History(ctx context.Context, resource string, pk any, limit int) ([]core.AuditEntry, error)
```
```python
def history(self, resource, pk, limit): ...
```

This is a separate, optional capability — the same shape as
`ListPage`/`list_page`. A write-only logger records silently and shows
nothing, which is the right arrangement when the log's real consumer is
a SIEM or a data warehouse rather than the admin UI.

The panel is a summary of recent activity, capped at ten entries. It is
not an audit browser: a full trail belongs wherever your log already
lives, with the querying and retention rules that come with it.
