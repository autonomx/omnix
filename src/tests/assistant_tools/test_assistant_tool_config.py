import pytest
from fastapi.testclient import TestClient

from app.assistant_tools.config_store import (
    AssistantActionConfigRecord,
    AssistantToolConfigRecord,
    AssistantToolsConfigPayload,
    default_assistant_tools_config,
    load_assistant_tools_config,
    save_assistant_tools_config,
)
from app.assistant_tools.credentials import load_assistant_tool_credentials
from app.gateway.main import create_gateway_app


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


def test_config_save_and_load_preserves_known_tool_settings(tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    request = AssistantToolsConfigPayload(
        tools=[
            AssistantToolConfigRecord(
                tool_id="gmail",
                enabled=True,
                connection_status="connected",
                actions=[
                    AssistantActionConfigRecord(action_id="gmail.read_email", enabled=True, approval_policy="allow_automatic"),
                    AssistantActionConfigRecord(action_id="gmail.send_email", enabled=True, approval_policy="always_ask"),
                ],
            )
        ]
    )

    saved = save_assistant_tools_config(request, path)
    loaded = load_assistant_tools_config(path)
    gmail = next(tool for tool in loaded.tools if tool.tool_id == "gmail")
    gmail_actions = {action.action_id: action for action in gmail.actions}

    assert saved == loaded
    assert gmail.enabled is True
    assert gmail.connection_status == "connected"
    assert gmail_actions["gmail.send_email"].enabled is True
    assert "calendar" in {tool.tool_id for tool in loaded.tools}


def test_assistant_tool_config_routes_persist_payload(monkeypatch, tmp_path):
    path = tmp_path / "assistant_tools_config.json"
    credentials_path = tmp_path / "assistant_tool_credentials.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(path))
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(credentials_path))
    client = TestClient(create_gateway_app())

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
    client = TestClient(create_gateway_app())

    response = client.get("/api/assistant/tools/connect/gmail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_id"] == "gmail"
    assert payload["provider"] == "Google"
    assert payload["configured"] is False
    assert payload["auth_url"] is None
    assert payload["redirect_uri"] == "http://testserver/api/assistant/tools/connect/google/callback"
    assert "Google OAuth is not configured" in payload["message"]


def test_assistant_tool_connect_route_builds_google_auth_url(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_GOOGLE_REDIRECT_URI", raising=False)
    client = TestClient(create_gateway_app())

    response = client.get("/api/assistant/tools/connect/gmail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["provider"] == "Google"
    assert payload["redirect_uri"] == "http://testserver/api/assistant/tools/connect/google/callback"
    assert payload["auth_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=client-123" in payload["auth_url"]
    assert "redirect_uri=http%3A%2F%2Ftestserver%2Fapi%2Fassistant%2Ftools%2Fconnect%2Fgoogle%2Fcallback" in payload["auth_url"]
    assert "gmail.modify" in payload["auth_url"]


def test_assistant_tool_oauth_client_route_saves_google_app_and_builds_auth_url(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_OAUTH_CLIENTS_PATH", str(tmp_path / "oauth_clients.json"))
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_GOOGLE_REDIRECT_URI", raising=False)
    client = TestClient(create_gateway_app())

    response = client.post(
        "/api/assistant/tools/connect/gmail/oauth-client",
        json={"client_id": "saved-client", "client_secret": "saved-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["auth_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=saved-client" in payload["auth_url"]


def test_assistant_tool_google_callback_reports_missing_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_GOOGLE_REDIRECT_URI", raising=False)
    client = TestClient(create_gateway_app())

    response = client.get("/api/assistant/tools/connect/google/callback?code=abc&state=gmail", follow_redirects=False)

    assert response.status_code == 303
    assert "assistant_tool_connected=0" in response.headers["location"]
    assert "Google+OAuth+callback+is+not+configured" in response.headers["location"]


def test_assistant_tool_google_callback_saves_account_and_credentials(monkeypatch, tmp_path):
    config_path = tmp_path / "assistant_tools_config.json"
    credentials_path = tmp_path / "assistant_tool_credentials.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(credentials_path))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-123")
    monkeypatch.delenv("OMNIX_ASSISTANT_TOOLS_GOOGLE_REDIRECT_URI", raising=False)
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CONNECT_RETURN_URL", "/chatbot")

    def fake_post_form_json(url, values, headers=None):
        assert url == "https://oauth2.googleapis.com/token"
        assert values["code"] == "abc"
        assert values["redirect_uri"] == "http://testserver/api/assistant/tools/connect/google/callback"
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid email profile https://www.googleapis.com/auth/gmail.modify",
        }

    def fake_get_bearer_json(url, access_token):
        assert url == "https://www.googleapis.com/oauth2/v2/userinfo"
        assert access_token == "access-token"
        return {"email": "ada@example.com", "name": "Ada Lovelace"}

    monkeypatch.setattr("app.assistant_tools.connections._post_form_json", fake_post_form_json)
    monkeypatch.setattr("app.assistant_tools.connections._get_bearer_json", fake_get_bearer_json)
    client = TestClient(create_gateway_app())

    response = client.get("/api/assistant/tools/connect/google/callback?code=abc&state=gmail", follow_redirects=False)

    assert response.status_code == 303
    assert "assistant_tool_connected=1" in response.headers["location"]
    gmail = next(tool for tool in load_assistant_tools_config(config_path).tools if tool.tool_id == "gmail")
    assert gmail.enabled is True
    assert gmail.connection_status == "connected"
    assert gmail.account_email == "ada@example.com"
    credential = next(record for record in load_assistant_tool_credentials(credentials_path).credentials if record.tool_id == "gmail")
    assert credential.access_token == "access-token"
    assert credential.refresh_token == "refresh-token"
    assert credential.account_email == "ada@example.com"
