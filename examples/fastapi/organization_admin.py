"""OrganizationAdmin: the relation target for UserAdmin.organization."""
from __future__ import annotations

from decimal import Decimal

from models import Organization, OrganizationRepository

from polyadmin import DateField, DecimalField, ModelAdmin, StringField
from polyadmin.core.inline import TabularInline

# Field.parse_form_value (polyadmin/core/field.py) already turns a posted
# "founded"/"balance" string into a date/Decimal before this admin ever
# sees it, and Field.validate() rejects one it can't parse -- "Enter a
# valid date."/"Enter a valid number." -- so create()/update() below never
# receive a malformed value to fall back on silently. Only "absent" (an
# optional field left blank posts as None) needs a default.


class OrganizationAdmin(ModelAdmin):
    model = Organization

    category = "Directory"

    list_display = ["id", "name", "founded", "balance"]
    form_fields = ["name", "founded", "balance"]
    search_fields = ["name"]
    fields = [
        StringField("name", required=True),
        DateField("founded"),
        DecimalField("balance"),
    ]
    # Shows each Organization's Users inline on its own
    # create/detail/edit pages -- see docs/inlines.md.
    inlines = [TabularInline("users", "organization")]

    def __init__(self, repository: OrganizationRepository) -> None:
        super().__init__()
        self.repository = repository

    def get_queryset(self):
        return self.repository.list()

    def get_object(self, pk):
        try:
            return self.repository.get(int(pk))
        except (TypeError, ValueError):
            return None

    def create(self, data):
        return self.repository.create(
            name=data["name"],
            founded=data.get("founded"),
            balance=data.get("balance") if data.get("balance") is not None else Decimal(0),
        )

    def update(self, obj, data):
        return self.repository.update(
            obj,
            name=data["name"],
            founded=data.get("founded"),
            balance=data.get("balance") if data.get("balance") is not None else Decimal(0),
        )
