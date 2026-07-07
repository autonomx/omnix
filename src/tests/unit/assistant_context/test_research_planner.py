from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.assist_core.hermes_client import HermesSidecarClient
import app.research.planner as planner_module
from app.research.planner import (
    ResearchOperation,
    ResearchPlan,
    ResearchPlanner,
    ResearchPlanningBudget,
    ResearchPlanningRequest,
    enforce_research_plan_budget,
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


def test_local_planner_uses_only_declarative_research_operations() -> None:
    decision = ResearchPlanner(prefer_hermes=False).plan(
        ResearchPlanningRequest(question="Compare the current options")
    )
    assert decision.backend == "local"
    assert [item.operation for item in decision.plan.operations] == [
        "web_search", "evaluate_evidence", "stop"
    ]


def test_budget_enforcement_caps_queries_steps_and_extracts() -> None:
    plan = ResearchPlan(
        objective="Bounded plan",
        operations=[
            ResearchOperation(operation="web_search", query="one"),
            ResearchOperation(operation="web_search", query="two"),
            ResearchOperation(operation="web_extract", source_record_id="source:one"),
            ResearchOperation(operation="web_extract", source_record_id="source:two"),
            ResearchOperation(operation="evaluate_evidence", evaluation_question="compare"),
        ],
    )
    bounded = enforce_research_plan_budget(
        plan,
        ResearchPlanningBudget(max_steps=4, max_queries=1, max_sources=3, max_extracts=1),
    )
    assert sum(item.operation == "web_search" for item in bounded.operations) == 1
    assert sum(item.operation == "web_extract" for item in bounded.operations) == 1
    assert len(bounded.operations) <= 4
    assert bounded.operations[-1].operation == "stop"


def test_unknown_research_operation_is_rejected_structurally() -> None:
    with pytest.raises(ValidationError):
        ResearchOperation.model_validate({"operation": "send_email", "reason": "not allowed"})


def test_hermes_research_prompt_contains_no_general_tool_catalog(monkeypatch) -> None:
    captured = {}
    response_plan = {
        "objective": "Compare current options",
        "operations": [
            {"operation": "web_search", "query": "current options", "reason": "find sources"},
            {"operation": "stop", "reason": "done"},
        ],
        "completion_conditions": ["Sources evaluated"],
    }

    def fake_post(url, headers, data, timeout):
        captured.update(json.loads(data))
        return FakeResponse(json.dumps(response_plan))

    monkeypatch.setattr("app.assist_core.hermes_client.requests.post", fake_post)
    plan = HermesSidecarClient().plan_research(
        ResearchPlanningRequest(question="Compare current options")
    )

    prompt = captured["messages"][1]["content"]
    assert plan.operations[0].operation == "web_search"
    assert "allowed_operations" in prompt
    assert "web_search" in prompt
    assert "send_email" not in prompt
    assert "gmail" not in prompt.lower()
    assert "hermes_catalog" not in prompt


def test_default_hermes_client_uses_runtime_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.assist_core.hermes_status.hermes_runtime_config",
        lambda: SimpleNamespace(
            base_url="http://127.0.0.1:9000",
            timeout_seconds=17.0,
        ),
    )
    monkeypatch.setenv("HERMES_API_KEY", "secret")

    client = planner_module._default_hermes_client()

    assert client.base_url == "http://127.0.0.1:9000"
    assert client.timeout == 17.0
    assert client.api_key == "secret"


def test_invalid_hermes_plan_falls_back_to_local_planner() -> None:
    class InvalidHermes:
        def plan_research(self, request):
            raise RuntimeError("invalid planner response")

    decision = ResearchPlanner(
        prefer_hermes=True,
        hermes_factory=lambda: InvalidHermes(),
    ).plan(ResearchPlanningRequest(question="Research this"))

    assert decision.backend == "local_fallback"
    assert decision.warnings == ["hermes_planner_unavailable:RuntimeError"]
    assert decision.plan.operations[0].operation == "web_search"
