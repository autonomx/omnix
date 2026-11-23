from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body
from pydantic import BaseModel, ConfigDict

from app.apps.rpg.edge.hermes.approved_command import RpgSubmitter, run_approved_command
from app.apps.rpg.edge.hermes.approved_config import hermes_rpg_approved_flow_config_payload
from app.apps.rpg.edge.hermes.execution_ledger import hermes_rpg_execution_ledger_recent
from app.apps.rpg.edge.hermes.assist_mode import hermes_assist_mode_policy
from app.apps.rpg.edge.hermes.context_pack import build_hermes_rpg_context_pack
from app.apps.rpg.edge.hermes.narrative_research import hermes_rpg_narrative_research_payload
from app.apps.rpg.edge.hermes.sequence_planner_loop import hermes_sequence_planner_loop
from app.apps.rpg.edge.hermes.sequence_approved_executor import hermes_rpg_sequence_execute_step_payload
from app.apps.rpg.edge.hermes.sequence_checkpoint_policy import hermes_sequence_checkpoint_policy
from app.apps.rpg.edge.hermes.sequence_contract import hermes_sequence_contract_validate
from app.apps.rpg.edge.hermes.sequence_gate import hermes_sequence_apply_gate
from app.apps.rpg.edge.hermes.sequence_loop_guard import hermes_sequence_loop_guard
from app.apps.rpg.edge.hermes.sequence_state import latest_hermes_sequence_state, save_hermes_sequence_state
from app.apps.rpg.edge.api.hermes_web_contracts import (
    HermesRpgApprovedFlowConfig,
    HermesRpgApprovedFlowResponse,
    HermesRpgExecutionLedgerResponse,
    HermesRpgSequenceResponse,
    HermesRpgSequenceStateResponse,
)
from app.apps.rpg.edge.api.web_contracts import documented
from app.apps.rpg.edge.api.route_contracts import (
    HermesNarrativeResearchResponse,
    HermesRpgContextPackResponse,
    HermesSequenceExecuteStepResponse,
    HermesSequencePlanResponse,
)

hermes_rpg_approved_bp = APIRouter()


def hermes_rpg_approved_flow_route_payload(
    payload: dict[str, Any] | None,
    *,
    submitter: RpgSubmitter | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return run_approved_command(payload, submitter=submitter, environ=environ)


def hermes_rpg_sequence_review_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    checked = hermes_sequence_contract_validate(data)
    sequence = checked["sequence"]
    gate = hermes_sequence_apply_gate(sequence) if checked["ok"] else None
    checkpoint = hermes_sequence_checkpoint_policy(sequence) if checked["ok"] else None
    loop_guard = hermes_sequence_loop_guard(sequence) if checked["ok"] else None
    assist_mode = hermes_assist_mode_policy(
        data.get("assist_mode"),
        checkpoint_reason=checkpoint.get("reason") if isinstance(checkpoint, dict) else None,
        high_risk=sequence.get("risk") == "high",
    ) if checked["ok"] else None
    review_ok = (
        checked["ok"]
        and bool(gate and gate.get("allowed") is True)
        and not bool(checkpoint and checkpoint.get("requires_checkpoint"))
        and not bool(loop_guard and loop_guard.get("ok") is False)
        and not bool(assist_mode and assist_mode.get("review_allowed") is False)
    )
    result = {
        "ok": review_ok,
        "source": "hermes_rpg_sequence_review_route",
        "validation": checked,
        "sequence": sequence,
        "gate": gate,
        "checkpoint": checkpoint,
        "loop_guard": loop_guard,
        "assist_mode": assist_mode,
        "state_changed": False,
    }
    session_id = data.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        result["sequence_state"] = save_hermes_sequence_state(session_id=session_id, review_payload=result)
    return result


class HermesRpgApprovedFlowRequest(BaseModel):
    """The approved-flow request; the flow validates its contents itself, so anything else passes through."""

    model_config = ConfigDict(extra="allow")

    enabled: bool | None = None
    user_step: dict[str, Any] | None = None
    replay_entry: dict[str, Any] | None = None
    context: dict[str, Any] | None = None


class HermesRpgSequenceRequest(BaseModel):
    """A sequence to review; ``hermes_sequence_contract_validate`` checks it, so anything else passes through."""

    model_config = ConfigDict(extra="allow")

    session_id: str | None = None
    assist_mode: str | None = None
    sequence_id: str | None = None
    objective: str | None = None
    domain: str | None = None
    state_owner: str | None = None
    risk: str | None = None
    status: str | None = None
    items: list[dict[str, Any]] | None = None


def _body(payload: BaseModel | None) -> dict[str, Any] | None:
    return payload.model_dump(exclude_unset=True) if payload is not None else None


@hermes_rpg_approved_bp.post("/api/hermes/rpg/approved-flow", responses=documented(HermesRpgApprovedFlowResponse))
def hermes_rpg_approved_flow_route(payload: HermesRpgApprovedFlowRequest | None = Body(default=None)) -> dict[str, Any]:
    return hermes_rpg_approved_flow_route_payload(_body(payload))


@hermes_rpg_approved_bp.get("/api/hermes/rpg/approved-flow/config", responses=documented(HermesRpgApprovedFlowConfig))
def hermes_rpg_approved_flow_config_route() -> dict[str, Any]:
    return hermes_rpg_approved_flow_config_payload()


@hermes_rpg_approved_bp.get("/api/hermes/rpg/approved-flow/ledger", responses=documented(HermesRpgExecutionLedgerResponse))
def hermes_rpg_approved_flow_ledger_route(limit: int = 20, session_id: str = "", sequence_id: str = "") -> dict[str, Any]:
    return hermes_rpg_execution_ledger_recent(limit, session_id=session_id or None, sequence_id=sequence_id or None)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/sequence/review", responses=documented(HermesRpgSequenceResponse))
def hermes_rpg_sequence_review_route(payload: HermesRpgSequenceRequest | None = Body(default=None)) -> dict[str, Any]:
    return hermes_rpg_sequence_review_payload(_body(payload))


@hermes_rpg_approved_bp.get("/api/hermes/rpg/sequence/state", responses=documented(HermesRpgSequenceStateResponse))
def hermes_rpg_sequence_state_route(session_id: str = "") -> dict[str, Any]:
    return latest_hermes_sequence_state(session_id=session_id)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/sequence/execute-step", responses=documented(HermesSequenceExecuteStepResponse))
def hermes_rpg_sequence_execute_step_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    return hermes_rpg_sequence_execute_step_payload(payload)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/context-pack", responses=documented(HermesRpgContextPackResponse))
def hermes_rpg_context_pack_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    session = raw_session if isinstance(raw_session := data.get("session"), dict) else data
    item_limit = int(data.get("item_limit") or 8)
    char_budget = int(data.get("char_budget") or 4000)
    return build_hermes_rpg_context_pack(session, item_limit=item_limit, char_budget=char_budget)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/sequence/plan", responses=documented(HermesSequencePlanResponse))
def hermes_rpg_sequence_plan_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    sequence = raw_sequence if isinstance(raw_sequence := data.get("sequence"), dict) else data
    context_pack = raw_context_pack if isinstance(raw_context_pack := data.get("context_pack"), dict) else {}
    return hermes_sequence_planner_loop(sequence, context_pack)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/narrative-research", responses=documented(HermesNarrativeResearchResponse))
def hermes_rpg_narrative_research_route(
    payload: dict[str, Any] | None = Body(default=None),
) -> dict[str, Any]:
    return hermes_rpg_narrative_research_payload(payload)
