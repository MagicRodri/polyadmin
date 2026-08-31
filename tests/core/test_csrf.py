import re

from polyadmin.core.csrf import (
    csrf_tokens_match,
    is_safe_method,
    new_csrf_token,
)

BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def test_new_csrf_token_is_random_and_url_safe():
    a, b = new_csrf_token(), new_csrf_token()
    assert a != b
    # 32 bytes, base64url, unpadded -- same shape as the Go side.
    assert len(a) == 43
    assert BASE64URL.match(a)


def test_is_safe_method():
    for method in ("GET", "HEAD", "OPTIONS", "TRACE", "get", "head"):
        assert is_safe_method(method)
    for method in ("POST", "PUT", "PATCH", "DELETE", "post", ""):
        assert not is_safe_method(method)


def test_csrf_tokens_match():
    assert csrf_tokens_match("abc", "abc")
    # Empty must never validate empty -- that is "no token at all".
    for a, b in (("abc", "abd"), ("abc", "ab"), ("", ""), ("abc", ""), ("", "abc"), (None, None)):
        assert not csrf_tokens_match(a, b)
