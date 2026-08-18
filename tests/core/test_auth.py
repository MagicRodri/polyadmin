from polyadmin.core.auth import AllowAllAuthenticator, DenyAllAuthenticator, Principal


def test_allow_all_authenticates_every_request():
    authenticator = AllowAllAuthenticator()
    assert authenticator.authenticate(request=object()) is not None


def test_allow_all_returns_the_configured_principal():
    principal = Principal(id="u1", display_name="Jane")
    authenticator = AllowAllAuthenticator(principal)
    assert authenticator.authenticate(request=object()) is principal


def test_deny_all_never_authenticates():
    authenticator = DenyAllAuthenticator()
    assert authenticator.authenticate(request=object()) is None
