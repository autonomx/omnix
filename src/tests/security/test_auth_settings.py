from __future__ import annotations

import pytest

from app.security.auth import (
    AUTH_ENFORCED_WHEN_UNSET,
    AuthConfigurationError,
    AuthMode,
    assert_auth_startup_allowed,
    resolve_auth_settings,
)


def test_unset_mode_keeps_legacy_behaviour_until_the_default_flip_is_approved() -> None:
    # Human gate (WP-4.1): flipping this constant is the approved default change.
    assert AUTH_ENFORCED_WHEN_UNSET is False
    settings = resolve_auth_settings({})
    assert settings.mode is AuthMode.LOCAL
    assert settings.explicit is False
    assert settings.enforced is False


@pytest.mark.parametrize("value", ["local", "LOCAL", " local "])
def test_explicit_local_mode_enforces_authentication(value: str) -> None:
    settings = resolve_auth_settings({"OMNIX_AUTH_MODE": value})
    assert settings.mode is AuthMode.LOCAL
    assert settings.enforced is True


def test_unknown_mode_fails_closed() -> None:
    with pytest.raises(AuthConfigurationError):
        resolve_auth_settings({"OMNIX_AUTH_MODE": "none"})


def test_session_lifetimes_default_to_twelve_hours_idle_and_seven_days_absolute() -> None:
    settings = resolve_auth_settings({"OMNIX_AUTH_MODE": "local"})
    assert settings.sliding_ttl_seconds == 12 * 3600
    assert settings.absolute_ttl_seconds == 7 * 86400


@pytest.mark.parametrize(
    ("env", "bind_host"),
    [
        ({"OMNIX_ENV": "test"}, "0.0.0.0"),
        ({"OMNIX_ENV": "development"}, "127.0.0.1"),
        ({"OMNIX_ENV": "development"}, "::1"),
        ({"OMNIX_ENV": "development"}, "localhost"),
    ],
)
def test_disabled_mode_is_allowed_only_for_tests_or_loopback_development(env, bind_host) -> None:
    source = {"OMNIX_AUTH_MODE": "disabled", **env}
    assert_auth_startup_allowed(resolve_auth_settings(source), bind_host=bind_host, env=source)


@pytest.mark.parametrize(
    ("env", "bind_host"),
    [
        ({"OMNIX_ENV": "development"}, "0.0.0.0"),
        ({"OMNIX_ENV": "development"}, None),
        ({"OMNIX_ENV": "production"}, "127.0.0.1"),
        ({}, "192.168.1.20"),
    ],
)
def test_disabled_mode_refuses_to_start_elsewhere(env, bind_host) -> None:
    source = {"OMNIX_AUTH_MODE": "disabled", **env}
    settings = resolve_auth_settings(source)
    assert settings.enforced is False
    with pytest.raises(AuthConfigurationError):
        assert_auth_startup_allowed(settings, bind_host=bind_host, env=source)


def test_oidc_mode_requires_issuer_client_and_redirect() -> None:
    with pytest.raises(AuthConfigurationError):
        resolve_auth_settings({"OMNIX_AUTH_MODE": "oidc", "OMNIX_OIDC_ISSUER": "https://idp.example"})


def test_oidc_issuer_must_use_https_off_loopback() -> None:
    with pytest.raises(AuthConfigurationError):
        resolve_auth_settings(
            {
                "OMNIX_AUTH_MODE": "oidc",
                "OMNIX_OIDC_ISSUER": "http://idp.example",
                "OMNIX_OIDC_CLIENT_ID": "omnix",
                "OMNIX_OIDC_REDIRECT_URI": "https://omnix.example/api/auth/oidc/callback",
            }
        )


@pytest.mark.parametrize("role", ["owner", "admin", "approver"])
def test_oidc_just_in_time_provisioning_never_mints_privileged_roles(role: str) -> None:
    with pytest.raises(AuthConfigurationError):
        resolve_auth_settings(
            {
                "OMNIX_AUTH_MODE": "oidc",
                "OMNIX_OIDC_ISSUER": "https://idp.example",
                "OMNIX_OIDC_CLIENT_ID": "omnix",
                "OMNIX_OIDC_REDIRECT_URI": "https://omnix.example/api/auth/oidc/callback",
                "OMNIX_OIDC_DEFAULT_ROLE": role,
            }
        )


def test_oidc_settings_resolve() -> None:
    settings = resolve_auth_settings(
        {
            "OMNIX_AUTH_MODE": "oidc",
            "OMNIX_OIDC_ISSUER": "https://idp.example/",
            "OMNIX_OIDC_CLIENT_ID": "omnix",
            "OMNIX_OIDC_REDIRECT_URI": "https://omnix.example/api/auth/oidc/callback",
            "OMNIX_OIDC_ALLOWED_DOMAINS": "Example.com, @corp.example",
        }
    )
    assert settings.enforced is True
    assert settings.oidc is not None
    assert settings.oidc.issuer == "https://idp.example"
    assert settings.oidc.allowed_domains == ("example.com", "corp.example")
    assert settings.oidc.default_role == "member"
