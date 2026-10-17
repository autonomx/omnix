"""Credential files on macOS: AES-GCM with a key in the login Keychain (MarketPulse S-8).

The Keychain itself is replaced by an in-memory fake; the encryption and every caller run for real.
"""
from __future__ import annotations

import os

import pytest

from app.security import keychain, provider_secret_store as store, service_credentials


class FakeKeychain:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], bytes] = {}
        self.adds = 0

    def find(self, service: str, account: str) -> bytes | None:
        return self.items.get((service, account))

    def add(self, service: str, account: str, secret: bytes) -> None:
        self.adds += 1
        self.items[(service, account)] = secret


@pytest.fixture
def mac(monkeypatch, tmp_path):
    fake = FakeKeychain()
    keychain.install_keychain_backend(fake)
    monkeypatch.setattr(store.sys, "platform", "darwin")
    monkeypatch.setenv("OMNIX_PROVIDER_SECRETS_PATH", str(tmp_path / "secrets" / "provider-api-keys.dpapi"))
    monkeypatch.setenv("OMNIX_KEYCHAIN_SERVICE", "MarketPulse-test")
    yield fake
    keychain.install_keychain_backend(None)


def test_values_round_trip_and_tampering_is_detected(mac):
    sealed = keychain.protect(b"sk-or-v1-secret")

    assert sealed.startswith(keychain.PREFIX) and b"sk-or-v1-secret" not in sealed
    assert keychain.unprotect(sealed) == b"sk-or-v1-secret"
    tampered = sealed[:-1] + bytes([sealed[-1] ^ 1])
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        keychain.unprotect(tampered)
    with pytest.raises(ValueError):
        keychain.unprotect(b"plain bytes")


def test_one_file_key_is_created_and_kept_in_the_keychain(mac):
    first = keychain.file_key()
    second = keychain.file_key()

    assert first == second and len(first) == 32
    assert mac.adds == 1
    assert ("MarketPulse-test", keychain.KEY_ACCOUNT) in mac.items


def test_provider_credentials_are_stored_encrypted_on_macos(mac, tmp_path, monkeypatch):
    monkeypatch.delenv("OMNIX_FRED_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert store.os_credential_store_available() is True
    assert store.credential_store_label() == "macOS Keychain"

    store.save_trading_provider_secrets("fred", {"api_key": "fred-on-mac"})

    raw = (tmp_path / "secrets" / "provider-api-keys.dpapi").read_bytes()
    assert b"fred-on-mac" not in raw
    assert store.load_trading_provider_secrets()["fred"] == {"api_key": "fred-on-mac"}


def test_service_credentials_are_protected_beside_the_provider_keys(mac, tmp_path, monkeypatch):
    # A Mac's files are the user's and 0600 (mkstemp); this Windows test machine reports neither, so present them so.
    real_fstat = service_credentials.os.fstat
    monkeypatch.setattr(service_credentials.os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(service_credentials.os, "fstat", lambda fd: os.stat_result(
        (0o100600, *tuple(real_fstat(fd))[1:4], 501, *tuple(real_fstat(fd))[5:])))
    path = service_credentials.service_credential_path()
    assert path == tmp_path / "secrets" / "service-token.protected"
    assert service_credentials.install_credential_path().name == "install-credential.protected"
    assert service_credentials.run_token_key_path().name == "run-token-key.protected"

    token = service_credentials.load_or_create_service_token()

    assert token.encode() not in path.read_bytes()
    assert service_credentials.load_or_create_service_token() == token


def test_without_windows_or_a_keychain_there_is_no_protected_store(monkeypatch):
    keychain.install_keychain_backend(None)
    monkeypatch.setattr(store.sys, "platform", "linux")

    assert store.os_credential_store_available() is False
    assert store.credential_store_label() == "environment only"
