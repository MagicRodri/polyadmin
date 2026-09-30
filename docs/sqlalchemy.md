# SQLAlchemy

`pip install "polyadmin[sqlalchemy]"`

`polyadmin.sqlalchemy.SQLAlchemyModelAdmin` serves a mapped class (SQLAlchemy 2.x declarative or
SQLModel `table=True`) from an async session factory.

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyadmin.core.field import ForeignKeyField
from polyadmin.core.filter import BooleanFilter, RelationFilter
from polyadmin.core.relation import Relation
from polyadmin.sqlalchemy import SQLAlchemyModelAdmin

sessions = async_sessionmaker(create_async_engine("postgresql+asyncpg://..."))


class ContractAdmin(SQLAlchemyModelAdmin):
    model = Contract
    session_factory = sessions
    list_display = ("id", "name", "company", "is_deleted")
    form_fields = ("name", "company", "is_deleted")
    search_fields = ("name",)
    filters = (BooleanFilter("is_deleted"), RelationFilter("company"))
    default_filters = {"is_deleted": False}
    fields = (ForeignKeyField("company", relation=Relation("company", target="companies", display_field="name")),)
```

The factory can also be passed per instance: `ContractAdmin(session_factory=sessions)`.

- Search, filters, ordering and paging run in SQL (`list_page`). Search matches `%` and `_`
  literally.
- `default_filters` apply until the user picks that filter, including "All"; each key must name a
  column, checked when the admin is constructed.
- Supported filters: `BooleanFilter`, `ChoiceFilter`, `EmptyFilter`, `DateFilter`, `RelationFilter`.
  Any other filter raises `TypeError` when the admin is constructed.
- Fields you don't declare are derived from the column type; a non-nullable column with no default
  is required.
- A relation field (`ForeignKeyField`/`OneToOneField`) writes the relationship's local FK column.
  Many-to-many fields are read-only.
- Writes load the row and flush through the ORM, so mapper events (`after_insert`, `after_update`,
  `after_delete`) fire for every create, edit, bulk edit and delete.
- A unique or foreign-key violation becomes a form error (`RecordFormError`) rather than a 500; a
  refused delete sends the user back to the delete page with the reason.
- A primary key the database rejects (out of the column's range, say) reads as "not found".
- Queries call SQLAlchemy's own `AsyncSession.execute`, so a SQLModel session doesn't warn.
