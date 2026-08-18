"""OrganizationAdmin: the relation target for UserAdmin.organization."""
from __future__ import annotations

from polyadmin import ModelAdmin, StringField
from polyadmin.core.inline import TabularInline

from models import Organization, OrganizationRepository


class OrganizationAdmin(ModelAdmin):
    model = Organization

    category = "Directory"

    list_display = ["id", "name"]
    form_fields = ["name"]
    search_fields = ["name"]
    fields = [StringField("name", required=True)]
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
        return self.repository.create(name=data["name"])
