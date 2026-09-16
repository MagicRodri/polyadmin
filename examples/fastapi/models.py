"""In-memory User/Organization models + repositories for the reference app.

A real application would back this with SQLAlchemy, SQLModel, or a
repository over its own database -- the admin core doesn't
care which. Kept intentionally simple here since the point of this
example is to exercise `admin`, not demonstrate an ORM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from itertools import count


@dataclass
class Organization:
    id: int
    name: str
    founded: date | None = None
    # A plain float, not Decimal: this is exactly the type
    # Field.parse_form_value (polyadmin/core/field.py) hands back for a
    # "decimal" field, and templating.py's decimal_display renders it as
    # fixed-point, shortest round-trip digits (matching Go's Balance
    # float64) -- manufacturing a Decimal here would buy nothing.
    balance: float = 0.0


class OrganizationRepository:
    def __init__(self) -> None:
        self._organizations: dict[int, Organization] = {}
        self._ids = count(1)

    def list(self) -> list[Organization]:
        return list(self._organizations.values())

    def get(self, pk: int) -> Organization | None:
        return self._organizations.get(pk)

    def delete(self, organization: Organization) -> None:
        del self._organizations[organization.id]

    def create(self, *, name: str, founded: date | None = None, balance: float = 0.0) -> Organization:
        organization = Organization(id=next(self._ids), name=name, founded=founded, balance=balance)
        self._organizations[organization.id] = organization
        return organization

    def update(self, organization: Organization, *, name: str, founded: date | None, balance: float) -> Organization:
        organization.name = name
        organization.founded = founded
        organization.balance = balance
        return organization


@dataclass
class Role:
    """The many-to-many target: a user holds any number of these.

    Modelled after the permissions list Django's admin is known for, and
    what the searchable multi-select on the user form is there to make
    bearable once the list is long.
    """

    id: int
    name: str


class RoleRepository:
    def __init__(self) -> None:
        self._roles: dict[int, Role] = {}
        self._ids = count(1)

    def list(self) -> list[Role]:
        return list(self._roles.values())

    def get(self, pk: int) -> Role | None:
        return self._roles.get(pk)

    def delete(self, role: Role) -> None:
        del self._roles[role.id]

    def create(self, *, name: str) -> Role:
        role = Role(id=next(self._ids), name=name)
        self._roles[role.id] = role
        return role


@dataclass
class User:
    id: int
    email: str
    is_active: bool = True
    # A plain choice field, so the reference app exercises ui/select
    # (the shadcn Select port). Every other choice-shaped field here is
    # a relation, which renders one of the two combobox widgets
    # instead -- without this, ui/select appeared nowhere in the app.
    plan: str = "Free"
    organization: Organization | None = None
    roles: list[Role] = field(default_factory=list)


class UserRepository:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._ids = count(1)

    def list(self) -> list[User]:
        return list(self._users.values())

    def get(self, pk: int) -> User | None:
        return self._users.get(pk)

    def create(
        self,
        *,
        email: str,
        is_active: bool = True,
        plan: str = "Free",
        organization: Organization | None = None,
        roles: list[Role] | None = None,
    ) -> User:
        user = User(
            id=next(self._ids),
            email=email,
            is_active=is_active,
            plan=plan,
            organization=organization,
            roles=list(roles or []),
        )
        self._users[user.id] = user
        return user

    def update(
        self,
        user: User,
        *,
        email: str | None,
        is_active: bool | None,
        plan: str | None = None,
        organization: Organization | None = None,
        roles: list[Role] | None = None,
    ) -> User:
        if email is not None:
            user.email = email
        if is_active is not None:
            user.is_active = is_active
        if plan is not None:
            user.plan = plan
        user.organization = organization
        user.roles = list(roles or [])
        return user

    def delete(self, user: User) -> None:
        del self._users[user.id]

    def matching(self, keep) -> list[User]:
        """The users keep accepts, in id order, so a preview's sample does not
        reshuffle between requests."""
        return sorted((u for u in self._users.values() if keep(u)), key=lambda u: u.id)


def seed(
    users: UserRepository,
    organizations: OrganizationRepository,
    roles: RoleRepository,
) -> None:
    # Founded in the same month for every organization: Task 15's browser
    # test checks that this date renders with a French month name under
    # the fr locale, and it doesn't matter which organization it looks at.
    founded = date(2019, 3, 1)
    acme = organizations.create(name="Acme Corp", founded=founded, balance=1234.5)
    widgets = organizations.create(name="Widgets Inc", founded=founded, balance=1234.5)
    globex = organizations.create(name="Globex Corporation", founded=founded, balance=1234.5)
    initech = organizations.create(name="Initech", founded=founded, balance=1234.5)

    # Enough roles that the multi-select's search box has something to
    # do -- the control only earns its keep past the point where
    # scanning the whole list stops being quick.
    administrator = roles.create(name="Administrator")
    billing = roles.create(name="Billing")
    support = roles.create(name="Support")
    roles.create(name="Auditor")
    roles.create(name="Content Editor")
    roles.create(name="Release Manager")
    roles.create(name="Read Only")
    security = roles.create(name="Security Officer")

    users.create(email="admin@example.com", is_active=True, plan="Enterprise", organization=acme, roles=[administrator, security])
    users.create(email="jane@example.com", is_active=True, plan="Pro", organization=acme, roles=[billing])
    users.create(email="john@example.com", is_active=False, plan="Free", organization=widgets)
    users.create(email="mary@example.com", is_active=True, plan="Pro", organization=widgets, roles=[support, billing])
    users.create(email="peter@example.com", is_active=True, plan="Enterprise", organization=globex, roles=[support])
    users.create(email="samir@example.com", is_active=True, plan="Free", organization=initech)
    users.create(email="milton@example.com", is_active=False, plan="Free", organization=None)
