"""In-memory User/Organization models + repositories for the reference app.

A real application would back this with SQLAlchemy, SQLModel, or a
repository over its own database -- the admin core doesn't
care which. Kept intentionally simple here since the point of this
example is to exercise `admin`, not demonstrate an ORM.
"""
from __future__ import annotations

from dataclasses import dataclass
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
class User:
    id: int
    email: str
    is_active: bool = True
    organization: Organization | None = None


class UserRepository:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._ids = count(1)

    def list(self) -> list[User]:
        return list(self._users.values())

    def get(self, pk: int) -> User | None:
        return self._users.get(pk)

    def create(self, *, email: str, is_active: bool = True, organization: Organization | None = None) -> User:
        user = User(id=next(self._ids), email=email, is_active=is_active, organization=organization)
        self._users[user.id] = user
        return user

    def update(
        self,
        user: User,
        *,
        email: str | None,
        is_active: bool | None,
        organization: Organization | None,
    ) -> User:
        if email is not None:
            user.email = email
        if is_active is not None:
            user.is_active = is_active
        user.organization = organization
        return user

    def delete(self, user: User) -> None:
        del self._users[user.id]


def seed(users: UserRepository, organizations: OrganizationRepository) -> None:
    acme = organizations.create(name="Acme Corp")
    widgets = organizations.create(name="Widgets Inc")
    globex = organizations.create(name="Globex Corporation")
    initech = organizations.create(name="Initech")
    users.create(email="admin@example.com", is_active=True, organization=acme)
    users.create(email="jane@example.com", is_active=True, organization=acme)
    users.create(email="john@example.com", is_active=False, organization=widgets)
    users.create(email="mary@example.com", is_active=True, organization=widgets)
    users.create(email="peter@example.com", is_active=True, organization=globex)
    users.create(email="samir@example.com", is_active=True, organization=initech)
    users.create(email="milton@example.com", is_active=False, organization=None)
