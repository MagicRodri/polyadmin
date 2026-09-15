import asyncio

from polyadmin.core._async import maybe_await


def test_maybe_await_returns_a_plain_value_unchanged():
    assert asyncio.run(maybe_await(42)) == 42


def test_maybe_await_returns_none_unchanged():
    assert asyncio.run(maybe_await(None)) is None


def test_maybe_await_awaits_a_coroutine():
    async def resolve():
        return "resolved"

    assert asyncio.run(maybe_await(resolve())) == "resolved"
