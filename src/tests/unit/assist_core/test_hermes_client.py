from __future__ import annotations

import json

from app.assist_core.core import AssistantRequest
from app.assist_core.hermes_client import HermesSidecarClient


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

    def post(url, *, headers, data, timeout):
        captured.update(json.loads(data))
        return _Response()

    monkeypatch.setattr("app.assist_core.hermes_client.requests.post", post)

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
