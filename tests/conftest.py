"""Shared test helpers.

`csrf` is imported explicitly (`from tests.conftest import csrf`) rather
than injected as a pytest fixture: it takes the client the test already
built, so there is nothing for pytest to supply. The template guard below
is the one autouse fixture.
"""

import jinja2
import pytest

from polyadmin.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, new_csrf_token

UNRENDERED_MARKERS = ("{{", "{%")


@pytest.fixture(autouse=True)
def no_unrendered_template_syntax(monkeypatch):
    """Fail any test whose rendering let Jinja syntax through as text.

    A string literal containing delimiters is never re-rendered, so it
    reaches the page verbatim -- `{% set x = "{{ ui(...) }}" %}` once put
    the raw expression into a class attribute. Leaks are collected and
    asserted at teardown rather than raised mid-render: the error-page
    renderer deliberately swallows exceptions, and would hide this one.
    """
    leaks = []
    original = jinja2.Template.render

    def render(self, *args, **kwargs):
        html = original(self, *args, **kwargs)
        leaks.extend(f"{self.name}: {marker!r}" for marker in UNRENDERED_MARKERS if marker in html)
        return html

    monkeypatch.setattr(jinja2.Template, "render", render)
    yield
    assert not leaks, f"unrendered Jinja syntax reached the output: {leaks}"


def csrf(client):
    """Give `client` a CSRF cookie and return the matching header.

    Usage: `client.post(url, data=..., headers=csrf(client))` -- the
    double-submit pair a real browser sends via the meta tag. The tests
    that assert *rejection* deliberately do not call this.
    """
    token = new_csrf_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}
