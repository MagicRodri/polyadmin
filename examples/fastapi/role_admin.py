"""RoleAdmin: the many-to-many target for UserAdmin's `roles` field.

It exists mainly so that field has a registered target to resolve
against -- a Relation names a slug, and the adapter looks that slug up
to turn each related object into a (pk, label) pair. It is a full
resource in its own right all the same: roles are editable like
anything else.
"""

from __future__ import annotations

from models import Role, RoleRepository, UserRepository

from polyadmin import DeleteGroup, DeletePreview, ModelAdmin, StringField


class RoleAdmin(ModelAdmin):
    model = Role

    category = "Directory"
    icon = "user"

    list_display = ["id", "name"]
    form_fields = ["name"]
    search_fields = ["name"]
    fields = [StringField("name", required=True)]

    def __init__(self, repository: RoleRepository, users: UserRepository) -> None:
        super().__init__()
        self.repository = repository
        self.users = users

    def delete_preview(self, objects):
        """A role still held by anyone is protected (docs/deletes.md)."""
        holders = self._holders(objects)
        return DeletePreview(protected=[DeleteGroup(resource="users", objects=holders, total=len(holders))])

    def delete(self, obj):
        # Storage keeps its own rule too, as a foreign-key constraint would.
        if self._holders([obj]):
            raise ValueError(f"Role {obj.name!r} is still assigned.")
        self.repository.delete(obj)

    def _holders(self, objects):
        doomed = {r.id for r in objects}
        return self.users.matching(lambda u: any(r.id in doomed for r in u.roles))

    def get_queryset(self):
        return self.repository.list()

    def get_object(self, pk):
        try:
            return self.repository.get(int(pk))
        except (TypeError, ValueError):
            return None

    def create(self, data):
        return self.repository.create(name=data["name"])
