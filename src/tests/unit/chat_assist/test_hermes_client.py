from __future__ import annotations

import json

import httpx

from app.platform.chat.assist.models import AssistantRequest
from app.platform.agent_runtime.evidence import _hermes_evidence_decision
from app.platform.chat.assist.hermes import HermesAssistantPlanner
from app.providers.hermes_client import HermesSidecarClient
from app.platform.research.planner import HermesResearchPlanner
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

    monkeypatch.setattr("app.providers.hermes_client.shared_http_client", lambda name: mock_http_client(handle))

    result = HermesAssistantPlanner().plan(
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


def _client_replying(monkeypatch, content, *, status: int = 200) -> list[dict]:
    captured: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        if status != 200:
            return httpx.Response(status, json={"error": "unavailable"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})

    monkeypatch.setattr("app.providers.hermes_client.shared_http_client", lambda name: mock_http_client(handle))
    return captured


def _research_request():
    from app.platform.research.planner import ResearchPlanningRequest

    return ResearchPlanningRequest(question="What is the current Rust release?")


def test_research_plan_accepts_fenced_json_and_sends_the_same_request(monkeypatch) -> None:
    fenced = "```json\n" + json.dumps({"objective": "Find the latest Rust release"}) + "\n```"
    captured = _client_replying(monkeypatch, fenced)

    plan = HermesResearchPlanner(HermesSidecarClient()).plan_research(_research_request())

    assert plan.objective == "Find the latest Rust release"
    assert set(captured[0]) == {"model", "stream", "messages"}
    assert captured[0]["model"] == "hermes-agent"


def test_an_invalid_research_plan_is_a_sidecar_error(monkeypatch) -> None:
    import pytest

    from app.providers.hermes_client import HermesSidecarError

    _client_replying(monkeypatch, json.dumps({"title": "no objective"}))
    with pytest.raises(HermesSidecarError, match="valid research plan"):
        HermesResearchPlanner(HermesSidecarClient()).plan_research(_research_request())


def test_an_http_failure_is_raised_unchanged(monkeypatch) -> None:
    import pytest

    _client_replying(monkeypatch, "", status=503)
    with pytest.raises(httpx.HTTPStatusError):
        HermesResearchPlanner(HermesSidecarClient()).plan_research(_research_request())


def test_evidence_decision_is_a_json_object(monkeypatch) -> None:
    import pytest

    from app.providers.hermes_client import HermesSidecarError

    captured = _client_replying(monkeypatch, json.dumps({"requirement": "none", "confidence": 0.9}))
    assert _hermes_evidence_decision(HermesSidecarClient(), "say hi", "chat")["requirement"] == "none"
    assert captured[0]["response_format"] == {"type": "json_object"}

    _client_replying(monkeypatch, json.dumps(["not", "an", "object"]))
    with pytest.raises(HermesSidecarError, match="valid evidence decision"):
        _hermes_evidence_decision(HermesSidecarClient(), "say hi", "chat")
