"""Mirrors go-polyadmin/core/login_test.go."""

import pytest

from polyadmin.core.login import safe_next_url


# safe_next_url is the guard on an open redirect, so the cases that
# matter are the hostile ones: every rejection must land back on
# base_path rather than anywhere an attacker chose.
@pytest.mark.parametrize(
    "next_url",
    [
        "https://evil.example/phish",
        "http://evil.example",
        # Scheme-relative: a URL, not a path, however much it looks like one.
        "//evil.example/phish",
        # Backslashes, which some browsers fold into forward slashes.
        "/\\evil.example",
        "\\\\evil.example",
        "/admin\\..\\..\\evil",
        # Real paths, but outside this admin.
        "/etc/passwd",
        "/other/app",
        # The prefix trap: starts with "/admin" as a string, different
        # route entirely.
        "/adminutes/secrets",
        # Nothing at all.
        "",
        None,
        "relative/path",
    ],
)
def test_safe_next_url_rejects_off_site_destinations(next_url):
    assert safe_next_url(next_url, "/admin") == "/admin"


@pytest.mark.parametrize(
    "next_url",
    [
        "/admin",
        "/admin/users",
        "/admin/users/7/edit",
        "/admin/users?page=3&sort=email",
    ],
)
def test_safe_next_url_keeps_destinations_inside_the_admin(next_url):
    assert safe_next_url(next_url, "/admin") == next_url


# Mounting at the root makes every absolute path "inside" the admin, but
# the off-site checks still have to hold -- that is the case where a
# sloppy prefix check would let anything through.
def test_safe_next_url_at_root_still_rejects_off_site():
    assert safe_next_url("/users", "/") == "/users"
    assert safe_next_url("//evil.example", "/") == "/"


# A trailing slash on the mount point must not change which destinations
# are considered inside it.
def test_safe_next_url_ignores_a_trailing_slash_on_base_path():
    assert safe_next_url("/admin/users", "/admin/") == "/admin/users"
