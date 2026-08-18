"""UserAdmin: wires the User repository into PolyAdmin.

Named `user_admin.py`, not `admin.py` -- a local `admin.py` would shadow
the installed `admin` package on sys.path.
"""

from __future__ import annotations

from polyadmin import BooleanField, EmailField, ModelAdmin
from polyadmin.core.action import Action
from polyadmin.core.field import ForeignKeyField
from polyadmin.core.filter import BooleanFilter
from polyadmin.core.relation import Relation
from models import OrganizationRepository, User, UserRepository

ORGANIZATION_RELATION = Relation(
    "organization", target="organizations", display_field="name"
)


def _set_active(model_admin: "UserAdmin", objects, active: bool) -> str:
    # In-memory repositories store the objects themselves, so mutating
    # in place is enough to persist -- no separate update() call needed.
    for obj in objects:
        obj.is_active = active
    verb = "Activated" if active else "Deactivated"
    return f"{verb} {len(objects)} user(s)."


def _activate(model_admin, objects, principal):
    return _set_active(model_admin, objects, True)


def _deactivate(model_admin, objects, principal):
    return _set_active(model_admin, objects, False)


class UserAdmin(ModelAdmin):
    model = User

    # Shares a sidebar accordion with OrganizationAdmin -- see
    # docs/routing.md's "Sidebar categories" section.
    category = "Directory"

    list_display = ["id", "email", "is_active", "organization"]
    detail_fields = ["id", "email", "is_active", "organization"]
    form_fields = ["email", "is_active", "organization"]
    search_fields = ["email"]
    filters = [BooleanFilter("is_active")]
    # Routes the "organization" relation through the /lookup endpoint
    # instead of a same-page <select> populated from every
    # organization -- demonstrates the combobox for a relation that, in
    # a real deployment, could be too large to dump wholesale.
    autocomplete_fields = ["organization"]
    actions = [
        Action("activate", _activate, label="Activate"),
        Action("deactivate", _deactivate, label="Deactivate", confirm="Deactivate the selected users?"),
    ]
    fields = [
        EmailField("email", required=True),
        BooleanField("is_active", default=True),
        ForeignKeyField("organization", relation=ORGANIZATION_RELATION),
    ]

    def __init__(
        self,
        repository: UserRepository,
        organization_repository: OrganizationRepository,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.organization_repository = organization_repository

    def get_queryset(self):
        return self.repository.list()

    def get_object(self, pk):
        try:
            return self.repository.get(int(pk))
        except (TypeError, ValueError):
            return None

    def _resolve_organization(self, data):
        pk = data.get("organization")
        if not pk:
            return None
        return self.organization_repository.get(int(pk))

    def create(self, data):
        return self.repository.create(
            email=data["email"],
            is_active=bool(data.get("is_active")),
            organization=self._resolve_organization(data),
        )

    def update(self, obj, data):
        return self.repository.update(
            obj,
            email=data.get("email"),
            is_active=data.get("is_active"),
            organization=self._resolve_organization(data),
        )

    def delete(self, obj):
        self.repository.delete(obj)
