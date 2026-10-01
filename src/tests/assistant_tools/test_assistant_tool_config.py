
import pytest
from fastapi.testclient import TestClient

from app.assistant_tools.config_store import (
    default_assistant_tools_config,
)
from app.assistant_tools import connections, proposals
from app.gateway.main import create_gateway_app
from app.persistence.tenant import TenantContext


@pytest.fixture(autouse=True)
def skip_local_env(monkeypatch):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_SKIP_LOCAL_ENV", "1")


def test_default_config_uses_safe_approval_policies():
    payload = default_assistant_tools_config()
    actions = {action.action_id: action for tool in payload.tools for action in tool.actions}

    assert actions["gmail.read_email"].enabled is True
    assert actions["gmail.read_email"].approval_policy == "allow_automatic"
    assert actions["gmail.create_draft"].approval_policy == "ask_sensitive"
    assert actions["gmail.send_email"].approval_policy == "always_ask"
    assert actions["gmail.delete_email"].enabled is False
    assert actions["calendar.delete_event"].enabled is False


def test_default_proposal_service_reads_current_tenant_each_call(monkeypatch):
    contexts = [
        TenantContext(
            user_id="user:first",
            workspace_id="workspace:first",
            membership_id="membership:first",
            roles=frozenset({"owner"}),
        ),
        TenantContext(
            user_id="user:second",
            workspace_id="workspace:second",
            membership_id="membership:second",
            roles=frozenset({"owner"}),
        ),
    ]
    monkeypatch.setattr(proposals, "default_database", lambda: object())
    monkeypatch.setattr(proposals, "current_tenant", lambda: contexts.pop(0))

    first = proposals.default_tool_proposal_service()
    second = proposals.default_tool_proposal_service()

    assert first is not second
    assert first.context.workspace_id == "workspace:first"
    assert second.context.workspace_id == "workspace:second"


@pytest.mark.postgres
def test_assistant_tool_config_routes_persist_payload(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    credentials_path = tmp_path / "assistant_tool_credentials.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(credentials_path))
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    initial = client.get("/api/assistant/tools/config")
    assert initial.status_code == 200
    payload = initial.json()
    gmail = next(tool for tool in payload["tools"] if tool["tool_id"] == "gmail")
    gmail["enabled"] = True
    gmail["connection_status"] = "connected"

    saved = client.post("/api/assistant/tools/config", json=payload)
    loaded = client.get("/api/assistant/tools/config")

    assert saved.status_code == 200
    assert loaded.status_code == 200
    saved_gmail = next(tool for tool in loaded.json()["tools"] if tool["tool_id"] == "gmail")
    assert saved_gmail["enabled"] is True
    assert saved_gmail["connection_status"] == "connected"


def test_assistant_tool_connect_route_reports_missing_google_oauth(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_GOOGLE_REDIRECT_URI", raising=False)
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    response = client.get("/api/assistant/tools/connect/gmail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_id"] == "gmail"
    assert payload["provider"] == "Google"
    assert payload["configured"] is False
    assert payload["auth_url"] is None
    assert payload["redirect_uri"] == "http://127.0.0.1/api/assistant/tools/connect/google/callback"
    assert "Google OAuth is not configured" in payload["message"]


def test_assistant_tool_connect_route_builds_google_auth_url(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_GOOGLE_REDIRECT_URI", raising=False)
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    response = client.get("/api/assistant/tools/connect/gmail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["provider"] == "Google"
    assert payload["redirect_uri"] == "http://127.0.0.1/api/assistant/tools/connect/google/callback"
    assert payload["auth_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=client-123" in payload["auth_url"]
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%2Fapi%2Fassistant%2Ftools%2Fconnect%2Fgoogle%2Fcallback" in payload["auth_url"]
    assert "gmail.modify" in payload["auth_url"]


def test_assistant_tool_google_callback_reports_missing_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_GOOGLE_REDIRECT_URI", raising=False)
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    response = client.get("/api/assistant/tools/connect/google/callback?code=abc&state=invalid", follow_redirects=False)

    assert response.status_code == 303
    assert "assistant_tool_connected=0" in response.headers["location"]
    assert "Google+OAuth+state+is+invalid+or+expired" in response.headers["location"]


def test_pending_oauth_states_are_size_and_ttl_bounded(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(connections.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(connections, "_MAX_PENDING_OAUTH_STATES", 2)
    monkeypatch.setattr(connections, "_OAUTH_STATE_TTL_SECONDS", 5.0)
    with connections._PENDING_OAUTH_LOCK:
        connections._PENDING_OAUTH_STATES.clear()

    first = connections._issue_oauth_state("google", "gmail")
    second = connections._issue_oauth_state("google", "calendar")
    third = connections._issue_oauth_state("google", "contacts")
    assert len(connections._PENDING_OAUTH_STATES) == 2
    assert connections._consume_oauth_state("google", first) is None
    assert connections._consume_oauth_state("google", second) == "calendar"
    assert connections._consume_oauth_state("google", second) is None

    clock[0] += 6
    assert connections._consume_oauth_state("google", third) is None
    assert not connections._PENDING_OAUTH_STATES
