from polyadmin.core.auth import Principal
from polyadmin.core.authorization import (
    AllowAllAuthorizer,
    DenyAllAuthorizer,
    SuperuserAuthorizer,
    resource_permission,
)


def test_resource_permission_naming():
    assert resource_permission("users", "view") == "users.view"


def test_allow_all_grants_everything():
    assert AllowAllAuthorizer().can(None, "users.delete") is True


def test_deny_all_denies_everything():
    assert DenyAllAuthorizer().can(Principal(id=1, is_superuser=True), "users.view") is False


def test_superuser_authorizer():
    authorizer = SuperuserAuthorizer()
    assert authorizer.can(Principal(id=1, is_superuser=True), "users.delete") is True
    assert authorizer.can(Principal(id=2, is_superuser=False), "users.delete") is False
    assert authorizer.can(None, "users.delete") is False
