from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid

import pytest

from app.agent_runtime.acceptance import evaluate_acceptance
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunSpec,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    ModelRef,
)
from app.agent_runtime.evidence import (
    build_evidence_receipt,
    evaluate_evidence_set,
    validate_required_evidence_capabilities,
)
from app.agent_runtime.semantic_classifier import classify_semantic_intent_safely
from app.agent_runtime.service import AgentRunService
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.agent_runtime.repository import PostgresAgentRunRepository


class _ExplodingClassifier:
    def classify(self, _content: str):
        raise TimeoutError("semantic provider timed out")


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timeout"),
        ValueError("malformed structured output"),
        RuntimeError("provider reset"),
    ],
)
def test_semantic_classifier_faults_fail_to_deterministic_fallback(error) -> None:
    class Classifier:
        def classify(self, _content: str):
            raise error

    assert classify_semantic_intent_safely(Classifier(), "fix the tests") is None


def test_evidence_provider_timeout_produces_no_receipt() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="release",
                source_class="software_release",
                freshness="current",
                trust_floor="primary",
                max_age_seconds=3600,
            )
        ],
    )
    receipt = build_evidence_receipt(
        run_id="run-fault",
        task_revision_id="revision-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "latest Python release"},
        result_payload={},
        error="timeout",
        requirement_id="release",
        source_class_hint="software_release",
    )
    assert receipt is None
    result = evaluate_evidence_set("run-fault", policy, [])
    assert result.passed is False
    assert result.missing_requirements == ["release"]


@pytest.mark.parametrize(
    "reason",
    ["missing_connection", "tool_disabled", "permission_denied", "rate_limited"],
)
def test_connector_preflight_denial_fails_closed(monkeypatch, reason: str) -> None:
    from app.assistant_tools import gate
    from app.assistant_tools.models import AssistantToolReviewDecision

    monkeypatch.setattr(
        gate,
        "review_assistant_tool_request",
        lambda request: AssistantToolReviewDecision(
            tool_id=request.tool_id,
            action_id=request.action_id,
            allowed=False,
            reason=reason,
        ),
    )
    with pytest.raises(Exception):
        validate_required_evidence_capabilities(["trading.market_quote"])


def test_partial_tool_completion_does_not_satisfy_acceptance() -> None:
    spec = AgentRunSpec(
        run_id="partial-tool",
        task="fix the tests",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
    )
    result = evaluate_acceptance(
        spec,
        events=[
            AgentEvent(
                run_id=spec.run_id,
                event_type="tool.started",
                payload={
                    "tool_call_id": "pytest",
                    "tool": "bash",
                    "args": {"command": "python -m pytest -q"},
                },
            )
        ],
        artifacts=[],
    )
    assert result.passed is False
    assert "successful_test_command" in result.failures


def test_failed_tool_exit_code_does_not_satisfy_acceptance() -> None:
    spec = AgentRunSpec(
        run_id="failed-tool",
        task="fix the tests",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "pytest",
                "tool": "bash",
                "args": {"command": "python -m pytest -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={
                "tool_call_id": "pytest",
                "tool": "bash",
                "is_error": False,
                "result": {"details": {"exitCode": 1}},
            },
        ),
    ]
    result = evaluate_acceptance(spec, events=events, artifacts=[])
    assert result.passed is False
    assert "successful_test_command" in result.failures


@pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for durable start-failure test",
)
def test_initial_runtime_start_failure_is_persisted_as_failed(monkeypatch) -> None:
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-agent-fault-tests",
        )
    )
    try:
        run_id = f"start-fault-{uuid.uuid4().hex}"
        service = AgentRunService(database, worker_id="fault-worker")
        monkeypatch.setattr(service, "_ensure_supervisor", lambda: None)
        monkeypatch.setattr(
            service.runtime,
            "start",
            lambda _spec: (_ for _ in ()).throw(RuntimeError("pi boot failed")),
        )

        spec = AgentRunSpec(
            run_id=run_id,
            task="research conceptually",
            profile="research",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with pytest.raises(RuntimeError, match="pi boot failed"):
            service.start(spec)

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            persisted = repository.get_run(run_id)
            work.rollback()
        assert persisted is not None
        assert persisted.status == "failed"
        assert "pi boot failed" in str(persisted.last_error)
    finally:
        database.close()


def test_stale_evidence_after_provider_delay_fails_current_requirement() -> None:
    now = datetime.now(timezone.utc)
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote",
                source_class="market_quote",
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=1,
            )
        ],
    )
    receipt = EvidenceReceipt(
        run_id="stale",
        capability_id="trading.market_quote",
        source_class="market_quote",
        request_digest="request",
        result_digest="result",
        trust_level="authoritative",
        observed_at=now.replace(year=now.year - 1),
        executed_at=now.replace(year=now.year - 1),
    )
    result = evaluate_evidence_set("stale", policy, [receipt], now=now)
    assert result.passed is False
    assert result.requirements[0].status == "stale"
