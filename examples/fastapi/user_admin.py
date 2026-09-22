"""UserAdmin: wires the User repository into PolyAdmin.

Named `user_admin.py`, not `admin.py` -- a local `admin.py` would shadow
the installed `admin` package on sys.path.
"""

from __future__ import annotations

from collections.abc import Sequence

from models import OrganizationRepository, RoleRepository, User, UserRepository

from polyadmin import BooleanField, EmailField, EnumField, ModelAdmin
from polyadmin.core.action import action
from polyadmin.core.auth import Principal
from polyadmin.core.field import ForeignKeyField, ManyToManyField
from polyadmin.core.filter import BooleanFilter, EmptyFilter, Filter, RelationFilter
from polyadmin.core.model_admin import Fieldset
from polyadmin.core.relation import Relation

ORGANIZATION_RELATION = Relation(
    "organization", target="organizations", display_field="name"
)
# cardinality="many" is what marks this as the collection side; the
# adapter reads the field's current value as a list and renders every
# role in the target's queryset as a choice.
ROLES_RELATION = Relation(
    "roles", target="roles", display_field="name", cardinality="many"
)


class PlanFilter(Filter):
    """A filter this application wrote itself: it subclasses the published
    base and implements the two methods, borrowing nothing from the
    framework's own filter types. This hook lets the admin supply both
    the options and the constraint itself.

    It exists in the example so the extension point is exercised by the
    browser suite rather than only described in docs/lists.md.
    """

    def choices_with_labels(self):
        return [("", "All"), ("paid", "Paid"), ("free", "Free")]

    def apply(self, objects, raw_value, model_admin):
        if not raw_value:
            return objects
        field = model_admin.get_field("plan")
        return [
            obj for obj in objects if (field.get_value(obj) != "Free") == (raw_value == "paid")
        ]


class UserAdmin(ModelAdmin):
    model = User

    # Shares a sidebar accordion with OrganizationAdmin -- see
    # docs/routing.md's "Sidebar categories" section.
    category = "Directory"

    list_display = ["id", "email", "is_active", "plan", "organization"]
    detail_fields = ["id", "email", "is_active", "plan", "organization", "roles"]
    # roles is on the form but not in list_display: a many-to-many
    # column costs a lookup per row and reads as noise in a table.
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
    filters = [
        BooleanFilter("is_active"),
        # organization is in autocomplete_fields below, so this renders as
        # the lookup-backed combobox rather than a list of every
        # organization.
        RelationFilter("organization"),
        # roles is a many-to-many: this matches a user holding the chosen
        # role among however many they have.
        RelationFilter("roles"),
        # Not every user has an organization, and "which ones are
        # unassigned?" is the question the seed makes real.
        EmptyFilter("organization"),
        # A filter this application wrote itself -- see PlanFilter.
        PlanFilter("plan"),
    ]
    # Routes the "organization" relation through the /lookup endpoint
    # instead of a same-page <select> populated from every
    # organization -- demonstrates the combobox for a relation that, in
    # a real deployment, could be too large to dump wholesale.
    autocomplete_fields = ["organization"]
    def _set_active(self, objects: Sequence[User], active: bool) -> str:
        # In-memory repositories store the objects themselves, so mutating
        # in place is enough to persist -- no separate update() call needed.
        for obj in objects:
            obj.is_active = active
        verb = "Activated" if active else "Deactivated"
        return f"{verb} {len(objects)} user(s)."

    @action(label="Activate")
    def activate(self, objects: Sequence[User], principal: Principal | None) -> str | None:
        return self._set_active(objects, True)

    @action(label="Deactivate", confirm="Deactivate the selected users?")
    def deactivate(self, objects: Sequence[User], principal: Principal | None) -> str | None:
        return self._set_active(objects, False)

    # The detail page offers Deactivate only; Activate stays a bulk action.
    detail_actions = ["deactivate"]
    fields = [
        # help_text is where an ORM/DB column comment lands. It shows
        # under the control on the form and under the label on the
        # detail page.
        EmailField("email", required=True,
                   help_text="Used to sign in, and the address notifications go to."),
        BooleanField("is_active", default=True,
                     help_text="Inactive users keep their data but cannot sign in."),
        # Enum + choices renders as ui/select: a hidden input carries the
        # value, so it posts like a native <select>.
        EnumField("plan", choices=["Free", "Pro", "Enterprise"], default="Free",
                  help_text="Determines feature limits and billing tier."),
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
