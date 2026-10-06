"""Disconnecting a tool account deletes its token and revokes the grant (ASVS 3.5.1)."""
from __future__ import annotations

import pytest

from app.platform.assistant_tools import connections
from app.platform.assistant_tools.config_store import default_assistant_tools_config
from app.platform.assistant_tools.credentials import AssistantToolCredentialRecord, credential_for_tool, upsert_tool_credential


@pytest.fixture
def tools(isolated_secret_store, monkeypatch):
    state = {"config": default_assistant_tools_config(), "revoked": []}
    monkeypatch.setattr(connections, "load_assistant_tools_config", lambda: state["config"])
    monkeypatch.setattr(connections, "save_assistant_tools_config", lambda payload: state.update(config=payload))

    def revoke(tool_id, credential):
        state["revoked"].append((tool_id, credential.refresh_token or credential.access_token))
        return True

    monkeypatch.setattr(connections, "_revoke_at_provider", revoke)
    return state


def _connect(tool_id: str, provider: str, token: str) -> None:
    upsert_tool_credential(AssistantToolCredentialRecord(
        tool_id=tool_id, provider=provider, access_token=token, refresh_token=f"refresh-{token}", updated_at="now"))
    connections._save_connected_account(tool_id, "Alice", "alice@example.com")


def _record(state, tool_id: str):
    return next(tool for tool in state["config"].tools if tool.tool_id == tool_id)


def test_disconnect_revokes_the_grant_and_deletes_the_token(tools) -> None:
    _connect("github", "GitHub", "gh-token")
    assert _record(tools, "github").connection_status == "connected"

    result = connections.disconnect_tool_account("github")

    assert result.revoked_at_provider is True
    assert tools["revoked"] == [("github", "refresh-gh-token")]
    assert credential_for_tool("github") is None
    record = _record(tools, "github")
    assert record.connection_status == "not_configured"
    assert record.account_email is None


def test_a_shared_google_grant_stays_while_another_google_tool_uses_it(tools) -> None:
    _connect("gmail", "Google", "mail-token")
    _connect("calendar", "Google", "calendar-token")

    result = connections.disconnect_tool_account("gmail")

    assert result.revoked_at_provider is False
    assert tools["revoked"] == []
    assert credential_for_tool("gmail") is None
    assert credential_for_tool("calendar") is not None
    assert "Revoke Omnix's access" in result.message

    assert connections.disconnect_tool_account("calendar").revoked_at_provider is True


def test_the_token_is_deleted_even_when_revocation_fails(tools, monkeypatch) -> None:
    monkeypatch.setattr(connections, "_revoke_at_provider", lambda tool_id, credential: False)
    _connect("github", "GitHub", "gh-token")

    result = connections.disconnect_tool_account("github")

    assert result.revoked_at_provider is False
    assert credential_for_tool("github") is None
