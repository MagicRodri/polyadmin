"""RoleAdmin: the many-to-many target for UserAdmin's `roles` field.

It exists mainly so that field has a registered target to resolve
against -- a Relation names a slug, and the adapter looks that slug up
to turn each related object into a (pk, label) pair. It is a full
resource in its own right all the same: roles are editable like
anything else.
"""

from __future__ import annotations

from polyadmin import ModelAdmin, StringField
from models import Role, RoleRepository


class RoleAdmin(ModelAdmin):
    model = Role

    category = "Directory"
    icon = "user"

    list_display = ["id", "name"]
    form_fields = ["name"]
    search_fields = ["name"]
    fields = [StringField("name", required=True)]

    def __init__(self, repository: RoleRepository) -> None:
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
