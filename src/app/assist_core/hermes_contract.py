from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .core import AssistantRequest, ToolCall, ToolRiskLevel

HermesRisk = Literal["low", "medium", "high", "simulation_truth"]
HermesState = Literal["accepted", "rejected", "fallback"]


@dataclass
class HermesToolSpec:
    name: str
    description: str
    risk: HermesRisk = "low"
    args_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class HermesPolicySpec:
    dry_run: bool = True
    allow_unknown_tools: bool = False
    review_required_for: list[HermesRisk] = field(default_factory=lambda: ["medium", "high", "simulation_truth"])


@dataclass
class HermesPlanRequest:
    workspace: str
    mode: str
    user_message: str
    session_id: str
    domain: str = "chat"
    dry_run: bool = True
    available_tools: list[HermesToolSpec] = field(default_factory=list)
    policy: HermesPolicySpec = field(default_factory=HermesPolicySpec)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class HermesPlanAction:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    risk: HermesRisk = "low"
    reason: str = ""


@dataclass
class HermesPlanResponse:
    state: HermesState
    response: str
    domain: str = "chat"
    actions: list[HermesPlanAction] = field(default_factory=list)
    requires_review: bool = False
    trace: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def hermes_request_from_assistant(
    request: AssistantRequest,
    *,
    available_tools: list[HermesToolSpec] | None = None,
    context: dict[str, Any] | None = None,
) -> HermesPlanRequest:
    return HermesPlanRequest(
        workspace="omnix",
        mode="chat_agent",
        user_message=request.message,
        session_id=request.session_id,
        domain=request.domain,
        dry_run=request.dry_run,
        available_tools=list(available_tools or []),
        policy=HermesPolicySpec(dry_run=request.dry_run),
        context=dict(context or request.metadata or {}),
    )


def hermes_request_payload(request: HermesPlanRequest) -> dict[str, Any]:
    return asdict(request)


def normalize_hermes_response(payload: dict[str, Any], *, fallback_domain: str = "chat") -> HermesPlanResponse:
    if not isinstance(payload, dict):
        return HermesPlanResponse(state="rejected", response="Hermes returned an invalid response.", error="invalid_response")
    actions = []
    for item in payload.get("actions", []) or []:
        if not isinstance(item, dict):
            continue
        actions.append(
            HermesPlanAction(
                tool=str(item.get("tool") or item.get("name") or ""),
                args=dict(item.get("args") or {}),
                risk=_risk(str(item.get("risk") or "low")),
                reason=str(item.get("reason") or ""),
            )
        )
    return HermesPlanResponse(
        state=_state(str(payload.get("state") or "accepted")),
        response=str(payload.get("response") or payload.get("final_message") or "I prepared a plan."),
        domain=str(payload.get("domain") or fallback_domain),
        actions=actions,
        requires_review=bool(payload.get("requires_review")),
        trace=dict(payload.get("trace") or {}),
        error=str(payload["error"]) if payload.get("error") else None,
    )


def tool_calls_from_hermes(response: HermesPlanResponse) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for action in response.actions:
        if action.tool:
            calls.append(ToolCall(name=action.tool, args=dict(action.args), risk=ToolRiskLevel(action.risk), reason=action.reason))
    return calls


def _risk(value: str) -> HermesRisk:
    return value if value in {"low", "medium", "high", "simulation_truth"} else "low"  # type: ignore[return-value]


def _state(value: str) -> HermesState:
    return value if value in {"accepted", "rejected", "fallback"} else "accepted"  # type: ignore[return-value]


def hermes_contract_schema() -> dict[str, Any]:
    return {
        "request": {
            "workspace": "omnix",
            "mode": "chat_agent",
            "user_message": "string",
            "session_id": "string",
            "domain": "string",
            "dry_run": "boolean",
            "available_tools": "list",
            "policy": "object",
            "context": "object",
        },
        "response": {
            "state": "accepted|rejected|fallback",
            "response": "string",
            "domain": "string",
            "actions": "list",
            "requires_review": "boolean",
            "trace": "object",
            "error": "string|null",
        },
    }
