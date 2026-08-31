"""Shared test helpers.

Imported explicitly (`from tests.conftest import csrf`) rather than
injected as a pytest fixture: it takes the client the test already built,
so there is nothing for pytest to supply.
"""

from polyadmin.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, new_csrf_token


def csrf(client):
    """Give `client` a CSRF cookie and return the matching header.

    Usage: `client.post(url, data=..., headers=csrf(client))` -- the
    double-submit pair a real browser sends via the meta tag. The tests
    that assert *rejection* deliberately do not call this.
    """
    token = new_csrf_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}
