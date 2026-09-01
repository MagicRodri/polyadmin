"""In-memory User/Organization models + repositories for the reference app.

A real application would back this with SQLAlchemy, SQLModel, or a
repository over its own database -- the admin core doesn't
care which. Kept intentionally simple here since the point of this
example is to exercise `admin`, not demonstrate an ORM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count


@dataclass
class Organization:
    id: int
    name: str


class OrganizationRepository:
    def __init__(self) -> None:
        self._organizations: dict[int, Organization] = {}
        self._ids = count(1)

    def list(self) -> list[Organization]:
        return list(self._organizations.values())

    def get(self, pk: int) -> Organization | None:
        return self._organizations.get(pk)

    def create(self, *, name: str) -> Organization:
        organization = Organization(id=next(self._ids), name=name)
        self._organizations[organization.id] = organization
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


def seed(
    users: UserRepository,
    organizations: OrganizationRepository,
    roles: RoleRepository,
) -> None:
    acme = organizations.create(name="Acme Corp")
    widgets = organizations.create(name="Widgets Inc")
    globex = organizations.create(name="Globex Corporation")
    initech = organizations.create(name="Initech")

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
