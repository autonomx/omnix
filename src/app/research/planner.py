"""Dedicated declarative planning for Deep Research."""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

ResearchOperationType = Literal["web_search", "web_extract", "evaluate_evidence", "stop"]


class ResearchPlanningBudget(BaseModel):
    max_steps: int = Field(default=6, ge=1, le=12)
    max_queries: int = Field(default=5, ge=1, le=10)
    max_sources: int = Field(default=12, ge=1, le=30)
    max_extracts: int = Field(default=8, ge=0, le=20)


class ResearchPlanningRequest(BaseModel):
    question: str = Field(min_length=1)
    budget: ResearchPlanningBudget = Field(default_factory=ResearchPlanningBudget)
    source_preferences: list[str] = Field(default_factory=list, max_length=8)
    evidence_summary: list[str] = Field(default_factory=list, max_length=20)


class ResearchOperation(BaseModel):
    operation: ResearchOperationType
    query: str | None = None
    source_record_id: str | None = None
    evaluation_question: str | None = None
    reason: str = ""


class ResearchPlan(BaseModel):
    objective: str
    operations: list[ResearchOperation] = Field(default_factory=list)
    completion_conditions: list[str] = Field(default_factory=list, max_length=8)
    stop_reason: str | None = None


class ResearchPlannerDecision(BaseModel):
    plan: ResearchPlan
    backend: Literal["hermes", "local_fallback", "local"]
    warnings: list[str] = Field(default_factory=list)


class LocalResearchPlanner:
    def plan_research(self, request: ResearchPlanningRequest) -> ResearchPlan:
        operations = [
            ResearchOperation(
                operation="web_search",
                query=request.question,
                reason="Find directly relevant current sources.",
            ),
            ResearchOperation(
                operation="evaluate_evidence",
                evaluation_question=(
                    "Which claims are supported by multiple sources, and where do sources conflict?"
                ),
                reason="Compare support, uncertainty, and conflicts before synthesis.",
            ),
            ResearchOperation(
                operation="stop",
                reason="Stop when the evidence is sufficient or the hard budget is exhausted.",
            ),
        ]
        return enforce_research_plan_budget(
            ResearchPlan(
                objective=request.question,
                operations=operations,
                completion_conditions=[
                    "At least one relevant source was evaluated.",
                    "Uncertainty and source conflicts are explicit.",
                    "The answer remains within the configured research budget.",
                ],
            ),
            request.budget,
        )


class ResearchPlanner:
    """Choose Hermes only through its dedicated research contract."""

    def __init__(
        self,
        *,
        hermes_factory: Callable[[], Any] | None = None,
        local_planner: LocalResearchPlanner | None = None,
        prefer_hermes: bool | None = None,
    ) -> None:
        self.hermes_factory = hermes_factory
        self.local_planner = local_planner or LocalResearchPlanner()
        self.prefer_hermes = _hermes_planner_enabled() if prefer_hermes is None else prefer_hermes

    def plan(self, request: ResearchPlanningRequest) -> ResearchPlannerDecision:
        if not self.prefer_hermes:
            return ResearchPlannerDecision(
                plan=self.local_planner.plan_research(request),
                backend="local",
            )
        warnings: list[str] = []
        try:
            client = self.hermes_factory() if self.hermes_factory else _default_hermes_client()
            plan = client.plan_research(request)
            return ResearchPlannerDecision(
                plan=enforce_research_plan_budget(plan, request.budget),
                backend="hermes",
            )
        except Exception as exc:
            warnings.append(f"hermes_planner_unavailable:{type(exc).__name__}")
            return ResearchPlannerDecision(
                plan=self.local_planner.plan_research(request),
                backend="local_fallback",
                warnings=warnings,
            )


def enforce_research_plan_budget(
    plan: ResearchPlan,
    budget: ResearchPlanningBudget,
) -> ResearchPlan:
    operations: list[ResearchOperation] = []
    query_count = 0
    extract_count = 0
    for operation in plan.operations:
        if len(operations) >= budget.max_steps:
            break
        if operation.operation == "web_search":
            if not operation.query or query_count >= budget.max_queries:
                continue
            query_count += 1
        if operation.operation == "web_extract":
            if not operation.source_record_id or extract_count >= budget.max_extracts:
                continue
            extract_count += 1
        operations.append(operation)
    if not operations or operations[-1].operation != "stop":
        if len(operations) >= budget.max_steps:
            operations[-1] = ResearchOperation(
                operation="stop",
                reason="Hard research step budget reached.",
            )
        else:
            operations.append(
                ResearchOperation(operation="stop", reason="Planner operations completed.")
            )
    return plan.model_copy(update={"operations": operations})


def research_plan_schema() -> dict[str, Any]:
    return ResearchPlan.model_json_schema()


def research_planning_payload(request: ResearchPlanningRequest) -> dict[str, Any]:
    return {
        "task": "Create a bounded declarative research plan. Do not execute operations.",
        "allowed_operations": ["web_search", "web_extract", "evaluate_evidence", "stop"],
        "schema": research_plan_schema(),
        "request": request.model_dump(mode="json"),
    }


def _default_hermes_client() -> Any:
    from app.assist_core.hermes_client import HermesSidecarClient
    from app.assist_core.hermes_status import hermes_runtime_config

    config = hermes_runtime_config()
    return HermesSidecarClient(
        base_url=config.base_url,
        api_key=os.environ.get("HERMES_API_KEY") or None,
        timeout=config.timeout_seconds,
    )


def _hermes_planner_enabled() -> bool:
    enabled = os.environ.get("HERMES_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    research = os.environ.get("OMNIX_DEEP_RESEARCH_HERMES_ENABLED", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
    return enabled and research
