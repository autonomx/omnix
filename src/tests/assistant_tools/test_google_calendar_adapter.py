from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.assistant_tools.calendar_adapter import GoogleCalendarRuntimeAdapter, run_calendar_tool_request
from app.assistant_tools.connections import google_access_token_for_tool
from app.assistant_tools.credentials import (
    AssistantToolCredentialRecord,
    AssistantToolOAuthClientRecord,
    credential_for_tool,
    upsert_oauth_client,
    upsert_tool_credential,
)
from app.assistant_tools.models import AssistantToolRequest


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_google_calendar_adapter_creates_real_api_payload(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr("app.assistant_tools.calendar_adapter.google_access_token_for_tool", lambda _tool_id: "token")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response(
            {
                "id": "google-event-1",
                "summary": "Planning",
                "start": {"dateTime": "2026-07-10T09:00:00"},
                "end": {"dateTime": "2026-07-10T09:30:00"},
                "htmlLink": "https://calendar.google.com/event?eid=1",
            }
        )

    monkeypatch.setattr("app.assistant_tools.calendar_adapter.urlopen", fake_urlopen)
    result = run_calendar_tool_request(
        AssistantToolRequest(
            tool_id="calendar",
            action_id="calendar.create_event",
            input={
                "title": "Planning",
                "start_time": "2026-07-10T09:00:00",
                "end_time": "2026-07-10T09:30:00",
                "timezone": "America/Vancouver",
                "reminder_minutes": 10,
            },
        ),
        adapter=GoogleCalendarRuntimeAdapter(),
    )

    assert result.error is None
    assert result.output["event"]["id"] == "google-event-1"
    assert captured["authorization"] == "Bearer token"
    assert captured["url"].endswith("/calendars/primary/events?sendUpdates=none")
    assert captured["body"]["reminders"]["overrides"] == [{"method": "popup", "minutes": 10}]


def test_google_access_token_refreshes_expired_credential(monkeypatch, tmp_path) -> None:
    credentials_path = tmp_path / "credentials.json"
    oauth_path = tmp_path / "oauth.json"
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH", str(credentials_path))
    monkeypatch.setenv("OMNIX_ASSISTANT_TOOLS_OAUTH_CLIENTS_PATH", str(oauth_path))
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    upsert_oauth_client(AssistantToolOAuthClientRecord(provider="google", client_id="client", client_secret="secret", updated_at="now"), oauth_path)
    upsert_tool_credential(
        AssistantToolCredentialRecord(
            tool_id="calendar",
            provider="Google",
            access_token="expired",
            refresh_token="refresh",
            expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            updated_at="then",
        ),
        credentials_path,
    )

    def fake_post(url, values, headers=None):
        assert values["grant_type"] == "refresh_token"
        assert values["refresh_token"] == "refresh"
        return {"access_token": "fresh", "expires_in": 3600, "token_type": "Bearer"}

    monkeypatch.setattr("app.assistant_tools.connections._post_form_json", fake_post)

    assert google_access_token_for_tool("calendar") == "fresh"
    assert credential_for_tool("calendar", credentials_path).access_token == "fresh"
