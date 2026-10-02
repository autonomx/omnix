"""Secret store and assistant-tool credentials (WP-4.9)."""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

from app.security import secrets
from app.security.secrets import (
    EnvSecretStore,
    SecretStoreUnavailable,
    create_secret_store,
    require_writable,
)

APP = Path(__file__).resolve().parents[2] / "app"


def test_env_store_is_read_only(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SECRET_ASSISTANT_TOOLS_W_CREDENTIALS", "value")
    store = EnvSecretStore()
    assert store.variable("assistant-tools/w/credentials") == "OMNIX_SECRET_ASSISTANT_TOOLS_W_CREDENTIALS"
    assert store.get("assistant-tools/w/credentials") == "value"
    with pytest.raises(SecretStoreUnavailable):
        store.set("x", "y")
    with pytest.raises(SecretStoreUnavailable):
        require_writable(store)


def test_secret_names_are_validated() -> None:
    for bad in ("", "../etc/passwd", "a" * 201, "name with spaces"):
        with pytest.raises(ValueError):
            EnvSecretStore().get(bad)


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_store_encrypts_at_rest(tmp_path) -> None:
    path = tmp_path / "secrets.dpapi"
    store = secrets.DpapiSecretStore(path)
    store.set("assistant-tools/w/credentials", "canary-token-value")
    store.set("other", "x")
    assert store.get("assistant-tools/w/credentials") == "canary-token-value"
    assert store.names() == ["assistant-tools/w/credentials", "other"]
    assert b"canary-token-value" not in path.read_bytes()
    store.delete("other")
    assert secrets.DpapiSecretStore(path).names() == ["assistant-tools/w/credentials"]


def test_keyring_store_uses_the_os_keychain(monkeypatch) -> None:
    saved: dict[tuple[str, str], str] = {}

    class PasswordDeleteError(Exception):
        pass

    fake = types.SimpleNamespace(
        get_password=lambda service, name: saved.get((service, name)),
        set_password=lambda service, name, value: saved.__setitem__((service, name), value),
        delete_password=lambda service, name: saved.pop((service, name)),
        errors=types.SimpleNamespace(PasswordDeleteError=PasswordDeleteError),
    )
    monkeypatch.setitem(sys.modules, "keyring", fake)
    store = secrets.KeyringSecretStore()
    store.set("a", "1")
    store.set("b", "2")
    assert (store.get("a"), store.names()) == ("1", ["a", "b"])
    store.delete("a")
    assert store.get("a") is None and store.names() == ["b"]


def test_store_selection(monkeypatch) -> None:
    assert isinstance(create_secret_store("env"), EnvSecretStore)
    with pytest.raises(ValueError):
        create_secret_store("plaintext")
    monkeypatch.setitem(sys.modules, "keyring", None)  # not installed
    with pytest.raises(SecretStoreUnavailable):
        create_secret_store("keyring")
    if sys.platform != "win32":
        assert isinstance(create_secret_store("auto"), EnvSecretStore)


def test_tool_credentials_are_kept_per_workspace(isolated_secret_store) -> None:
    from app.assistant_tools.credentials import (
        AssistantToolCredentialRecord,
        credential_for_tool,
        delete_tool_credential,
        upsert_tool_credential,
    )
    from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant

    record = AssistantToolCredentialRecord(tool_id="gmail", provider="google", access_token="t", updated_at="now")
    upsert_tool_credential(record)
    assert credential_for_tool("gmail").access_token == "t"
    token = push_tenant(TenantContext(user_id="u", workspace_id="workspace:other", membership_id="m",
                                      roles=frozenset({"owner"})))
    try:
        assert credential_for_tool("gmail") is None
    finally:
        pop_tenant(token)
    assert any(name.startswith("assistant-tools/workspace:local/") for name in isolated_secret_store.names())
    delete_tool_credential("gmail")
    assert credential_for_tool("gmail") is None


def test_credentials_never_touch_files() -> None:
    """No plaintext backend: the credentials module performs no file writes."""
    tree = ast.parse((APP / "assistant_tools" / "credentials.py").read_text(encoding="utf-8"))
    calls = {
        getattr(node.func, "attr", getattr(node.func, "id", ""))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not calls & {"write_text", "write_bytes", "open", "dump", "mkdir"}
