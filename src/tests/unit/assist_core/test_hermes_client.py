from __future__ import annotations

import json

import httpx

from app.assist_core.core import AssistantRequest
from app.assist_core.hermes_client import HermesSidecarClient
from tests.support.http import mock_http_client


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "state": "accepted",
                                "response": "Review this proposal.",
                                "domain": "chat",
                                "actions": [],
                                "requires_review": True,
                                "trace": {},
                                "error": None,
                            }
                        )
                    }
                }
            ]
        }


def test_plan_requests_strict_nonexecuting_json(monkeypatch) -> None:
    captured: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_Response().json())

    monkeypatch.setattr("app.assist_core.hermes_client.shared_http_client", lambda name: mock_http_client(handle))

    result = HermesSidecarClient().plan(
        AssistantRequest(
            message="Create a reminder for six.",
            session_id="chat:test",
            dry_run=True,
        )
    )

    system_prompt = captured["messages"][0]["content"]
    assert captured["response_format"] == {"type": "json_object"}
    assert "Never execute tools" in system_prompt
    assert "entire final answer MUST be one JSON object" in system_prompt
    assert "only allowlisted tools" in system_prompt
    assert result.success is True
    assert result.requires_confirmation is True
