"""delete_selected's failure message reads in the request's language."""

import pytest

from polyadmin.i18n import GettextTranslator, use_locale
from tests.core.test_model_admin import InMemoryUserAdmin


class FailingUserAdmin(InMemoryUserAdmin):
    def delete(self, obj):
        raise ValueError("disk full")


@pytest.mark.parametrize(
    "locale, expected",
    [("en", "then failed"), ("fr", "puis échec"), ("ru", "затем сбой")],
)
def test_failure_message_is_translated(locale, expected):
    model_admin = FailingUserAdmin()
    user = model_admin.create({"email": "a@example.com"})
    with use_locale(locale, GettextTranslator()), pytest.raises(RuntimeError) as caught:
        model_admin.delete_selected([user], None)
    assert expected in str(caught.value)
    assert "disk full" in str(caught.value)
