"""UserAdmin: wires the User repository into PolyAdmin.

Named `user_admin.py`, not `admin.py` -- a local `admin.py` would shadow
the installed `admin` package on sys.path.
"""

from __future__ import annotations

from polyadmin import BooleanField, EmailField, EnumField, ModelAdmin
from polyadmin.core.action import Action
from polyadmin.core.field import ForeignKeyField, ManyToManyField
from polyadmin.core.filter import BooleanFilter
from polyadmin.core.model_admin import Fieldset
from polyadmin.core.relation import Relation
from models import OrganizationRepository, RoleRepository, User, UserRepository

ORGANIZATION_RELATION = Relation(
    "organization", target="organizations", display_field="name"
)
# cardinality="many" is what marks this as the collection side; the
# adapter reads the field's current value as a list and renders every
# role in the target's queryset as a choice.
ROLES_RELATION = Relation(
    "roles", target="roles", display_field="name", cardinality="many"
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

    list_display = ["id", "email", "is_active", "plan", "organization"]
    detail_fields = ["id", "email", "is_active", "plan", "organization", "roles"]
    # roles is on the form but not in list_display: a many-to-many
    # column costs a lookup per row and reads as noise in a table, which
    # is why Django keeps it off list_display too.
    # Grouped rather than flat, to exercise fieldsets -- the other
    # admins in this app stay flat, so both paths have example coverage.
    # Declaring these replaces form_fields: the groups are the form's
    # field list.
    fieldsets = [
        Fieldset(fields=["email", "is_active"]),
        Fieldset(
            title="Membership",
            description="Where this user belongs and what they may do.",
            fields=["plan", "organization", "roles"],
        ),
    ]
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
        # Enum + choices renders as ui/select: a hidden input carries the
        # value, so it posts like a native <select>.
        EnumField("plan", choices=["Free", "Pro", "Enterprise"], default="Free"),
        ForeignKeyField("organization", relation=ORGANIZATION_RELATION),
        # Renders as the searchable multi-select
        # (components/ui/multi-select.html) -- the whole point of
        # seeding eight roles in models.py.
        ManyToManyField("roles", relation=ROLES_RELATION),
    ]

    def __init__(
        self,
        repository: UserRepository,
        organization_repository: OrganizationRepository,
        role_repository: RoleRepository,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.organization_repository = organization_repository
        self.role_repository = role_repository

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

    def _resolve_roles(self, data):
        """Turn the posted pks back into role objects.

        The form posts one value per selection under "roles" (exactly
        what a <select multiple> posted), which parse_form_data hands
        over as a list of strings.
        """
        resolved = []
        for pk in data.get("roles") or []:
            try:
                role = self.role_repository.get(int(pk))
            except (TypeError, ValueError):
                continue
            if role is not None:
                resolved.append(role)
        return resolved

    def create(self, data):
        return self.repository.create(
            email=data["email"],
            is_active=bool(data.get("is_active")),
            plan=data.get("plan") or "Free",
            organization=self._resolve_organization(data),
            roles=self._resolve_roles(data),
        )

    def update(self, obj, data):
        return self.repository.update(
            obj,
            email=data.get("email"),
            is_active=data.get("is_active"),
            plan=data.get("plan"),
            organization=self._resolve_organization(data),
            roles=self._resolve_roles(data),
        )

    def delete(self, obj):
        self.repository.delete(obj)
