from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body

from .hermes_rpg_approved_config import (
    hermes_rpg_approved_flow_config_payload,
    hermes_rpg_approved_flow_feature_enabled,
)
from .hermes_rpg_approved_flow import hermes_rpg_approved_flow
from .hermes_rpg_canonical_submitter import hermes_rpg_canonical_submitter
from .hermes_rpg_execution_ledger import hermes_rpg_execution_ledger_recent, hermes_rpg_execution_ledger_record
from .hermes_rpg_flow_readout import hermes_rpg_flow_readout
from .hermes_rpg_submit_bridge import RpgSubmitter
from .hermes_assist_mode import hermes_assist_mode_policy
from .hermes_rpg_context_pack import build_hermes_rpg_context_pack
from .hermes_sequence_planner_loop import hermes_sequence_planner_loop
from .hermes_sequence_approved_executor import hermes_rpg_sequence_execute_step_payload
from .hermes_sequence_checkpoint_policy import hermes_sequence_checkpoint_policy
from .hermes_sequence_contract import hermes_sequence_contract_validate
from .hermes_sequence_gate import hermes_sequence_apply_gate
from .hermes_sequence_loop_guard import hermes_sequence_loop_guard
from .hermes_sequence_state import latest_hermes_sequence_state, save_hermes_sequence_state

hermes_rpg_approved_bp = APIRouter()


def hermes_rpg_approved_flow_enabled(
    payload: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    return payload.get("enabled") is True and hermes_rpg_approved_flow_feature_enabled(environ)


def hermes_rpg_approved_flow_route_payload(
    payload: dict[str, Any] | None,
    *,
    submitter: RpgSubmitter | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    config = hermes_rpg_approved_flow_config_payload(environ)
    if not hermes_rpg_approved_flow_enabled(data, environ=environ):
        return {
            "ok": False,
            "source": "hermes_rpg_approved_flow_route",
            "error": "hermes_rpg_approved_flow_disabled",
            "enabled": False,
            "config": config,
            "state_changed": False,
        }

    user_step = data.get("user_step") if isinstance(data.get("user_step"), dict) else {}
    replay_entry = data.get("replay_entry") if isinstance(data.get("replay_entry"), dict) else {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    flow = hermes_rpg_approved_flow(
        user_step,
        replay_entry,
        context,
        submitter or hermes_rpg_canonical_submitter,
    )
    readout = hermes_rpg_flow_readout(flow)
    ledger_entry = hermes_rpg_execution_ledger_record(payload=data, config=config, flow=flow, readout=readout)
    return {
        "ok": flow.get("ok") is True,
        "source": "hermes_rpg_approved_flow_route",
        "enabled": True,
        "config": config,
        "flow": flow,
        "readout": readout,
        "ledger_entry": ledger_entry,
        "state_changed": flow.get("state_changed") is True,
    }


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


@hermes_rpg_approved_bp.post("/api/hermes/rpg/approved-flow")
def hermes_rpg_approved_flow_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    return hermes_rpg_approved_flow_route_payload(payload)


@hermes_rpg_approved_bp.get("/api/hermes/rpg/approved-flow/config")
def hermes_rpg_approved_flow_config_route() -> dict[str, object]:
    return hermes_rpg_approved_flow_config_payload()


@hermes_rpg_approved_bp.get("/api/hermes/rpg/approved-flow/ledger")
def hermes_rpg_approved_flow_ledger_route(limit: int = 20, session_id: str = "", sequence_id: str = "") -> dict[str, object]:
    return hermes_rpg_execution_ledger_recent(limit, session_id=session_id or None, sequence_id=sequence_id or None)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/sequence/review")
def hermes_rpg_sequence_review_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
    return hermes_rpg_sequence_review_payload(payload)


@hermes_rpg_approved_bp.get("/api/hermes/rpg/sequence/state")
def hermes_rpg_sequence_state_route(session_id: str = "") -> dict[str, object]:
    return latest_hermes_sequence_state(session_id=session_id)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/sequence/execute-step")
def hermes_rpg_sequence_execute_step_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
    return hermes_rpg_sequence_execute_step_payload(payload)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/context-pack")
def hermes_rpg_context_pack_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
    data = payload if isinstance(payload, dict) else {}
    session = data.get("session") if isinstance(data.get("session"), dict) else data
    item_limit = int(data.get("item_limit") or 8)
    char_budget = int(data.get("char_budget") or 4000)
    return build_hermes_rpg_context_pack(session, item_limit=item_limit, char_budget=char_budget)


@hermes_rpg_approved_bp.post("/api/hermes/rpg/sequence/plan")
def hermes_rpg_sequence_plan_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
    data = payload if isinstance(payload, dict) else {}
    sequence = data.get("sequence") if isinstance(data.get("sequence"), dict) else data
    context_pack = data.get("context_pack") if isinstance(data.get("context_pack"), dict) else {}
    return hermes_sequence_planner_loop(sequence, context_pack)
