from concurrent.futures import ThreadPoolExecutor
import os
import re
import secrets
import stat
from types import SimpleNamespace

import pytest

from app.security import service_credentials as credentials


@pytest.fixture
def protected_store(monkeypatch, tmp_path):
    # Exercise publication races with deterministic fake OS encryption; the
    # native protection contract is checked separately below.
    monkeypatch.setattr(credentials, "_windows", lambda: True)
    monkeypatch.setattr(credentials.provider_secret_store, "_protect", lambda value: b"protected:" + value[::-1])
    monkeypatch.setattr(credentials.provider_secret_store, "_unprotect", lambda value: value[len(b"protected:"):][::-1])
    return tmp_path / "secure" / "service-token.dpapi"


def test_service_token_is_random_and_reused(protected_store):
    first = credentials.load_or_create_service_token(protected_store)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", first)
    assert first.encode() not in protected_store.read_bytes()
    assert credentials.load_or_create_service_token(protected_store) == first
    assert list(protected_store.parent.glob(".service-token-*")) == []


def test_concurrent_launchers_publish_one_complete_credential(protected_store):
    with ThreadPoolExecutor(max_workers=8) as executor:
        tokens = list(executor.map(lambda _: credentials.load_or_create_service_token(protected_store), range(8)))
    assert len(set(tokens)) == 1
    assert credentials.load_or_create_service_token(protected_store) == tokens[0]
    assert list(protected_store.parent.glob(".service-token-*")) == []


def test_invalid_existing_credential_is_not_silently_replaced(protected_store):
    protected_store.parent.mkdir()
    protected_store.write_bytes(b"plaintext-invalid")
    with pytest.raises(credentials.ServiceCredentialError, match="format_invalid"):
        credentials.load_or_create_service_token(protected_store)
    assert protected_store.read_bytes() == b"plaintext-invalid"


def test_environment_token_overrides_store_without_reading_or_writing(monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    monkeypatch.setattr(credentials, "load_or_create_service_token", lambda: pytest.fail("configured token must not access storage"))
    assert credentials.initialize_service_token() == token


@pytest.mark.parametrize("value", ["", "short", "a" * 32, "a" * 42, "a" * 43 + " ", "a" * 43 + "+"])
def test_invalid_environment_configuration_fails_closed(monkeypatch, value):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", value)
    monkeypatch.setattr(credentials, "load_or_create_service_token", lambda: pytest.fail("invalid configuration must not generate a replacement"))
    with pytest.raises(credentials.ServiceCredentialError, match="invalid_service_token_configuration"):
        credentials.initialize_service_token()


def test_launcher_initialization_exports_stored_token(monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.delenv("OMNIX_SERVICE_TOKEN", raising=False)
    monkeypatch.setattr(credentials, "load_or_create_service_token", lambda: token)
    assert credentials.initialize_service_token() == token
    assert os.environ["OMNIX_SERVICE_TOKEN"] == token
    monkeypatch.delenv("OMNIX_SERVICE_TOKEN")


@pytest.mark.parametrize("mode", ["oidc", "disabled", "unknown"])
def test_nonlocal_mode_requires_an_explicit_service_credential(monkeypatch, mode):
    monkeypatch.delenv("OMNIX_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("OMNIX_AUTH_MODE", mode)
    monkeypatch.setattr(credentials, "load_or_create_service_token", lambda: pytest.fail("nonlocal launch must not generate a local token"))
    with pytest.raises(credentials.ServiceCredentialError, match="required_for_nonlocal_mode"):
        credentials.initialize_service_token()


def test_native_os_store_protects_the_generated_credential(tmp_path):
    path = tmp_path / "native" / "service-token"
    token = credentials.load_or_create_service_token(path)
    assert credentials.load_or_create_service_token(path) == token
    if credentials._windows():
        assert path.read_bytes().startswith(credentials._WINDOWS_PREFIX)
        assert token.encode() not in path.read_bytes()
    else:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_posix_unsafe_permissions_are_rejected(monkeypatch, tmp_path):
    path = tmp_path / "service-token"
    path.write_text(secrets.token_urlsafe(32))
    monkeypatch.setattr(credentials, "_windows", lambda: False)
    monkeypatch.setattr(credentials.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(credentials.os, "fstat", lambda _: SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=1000))
    with pytest.raises(credentials.ServiceCredentialError, match="permissions_unsafe"):
        credentials.load_or_create_service_token(path)
