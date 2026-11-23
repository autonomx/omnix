"""An approved Hermes command, run on the RPG turn path (RQ-1.6).

``run_approved_command`` is the one way an approved command reaches the game. In a single call it checks that the
approved flow is switched on (``HERMES_RPG_APPROVED_FLOW_ENABLED`` and the payload's ``enabled``), that the user step
is ready, the replay entry passed and the command and campaign are named; submits the command; and records the
execution in the ledger. A caller cannot submit without the check, or check without the record.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.apps.rpg.edge.hermes.approved_config import hermes_rpg_approved_flow_config_payload
from app.apps.rpg.edge.hermes.execution_ledger import hermes_rpg_execution_ledger_record
from app.apps.rpg.foundation.safe_values import clean_text, mapping_copy, safe_dict

RpgSubmitter = Callable[[dict[str, Any]], dict[str, Any]]

_SOURCE = "hermes_rpg_approved_flow_route"


def run_approved_command(
    payload: Mapping[str, Any] | None,
    *,
    submitter: RpgSubmitter | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Check, submit and record one approved command: ``payload`` holds ``enabled``, ``user_step``,
    ``replay_entry`` and ``context`` (the campaign's ``session_id``, its ``context_hash``, the approval source)."""
    data = mapping_copy(payload)
    config = hermes_rpg_approved_flow_config_payload(environ)
    if data.get("enabled") is not True or config.get("enabled") is not True:
        return {"ok": False, "source": _SOURCE, "error": "hermes_rpg_approved_flow_disabled", "enabled": False,
                "config": config, "state_changed": False}
    if submitter is None:
        from app.apps.rpg.edge.hermes.canonical_submitter import hermes_rpg_canonical_submitter

        submitter = hermes_rpg_canonical_submitter
    flow = _approved_flow(safe_dict(data.get("user_step")), safe_dict(data.get("replay_entry")),
                          safe_dict(data.get("context")), submitter)
    readout = _readout(flow)
    ledger_entry = hermes_rpg_execution_ledger_record(payload=data, config=config, flow=flow, readout=readout)
    return {"ok": flow["ok"], "source": _SOURCE, "enabled": True, "config": config, "flow": flow,
            "readout": readout, "ledger_entry": ledger_entry, "state_changed": flow["state_changed"]}


def _approved_flow(user_step: dict[str, Any], replay_entry: dict[str, Any], context: dict[str, Any],
                   submitter: RpgSubmitter) -> dict[str, Any]:
    command = clean_text(replay_entry.get("command_text") or user_step.get("command_text"))
    session_id = clean_text(context.get("session_id"))
    context_hash = context.get("context_hash") or None
    ready = (user_step.get("ready") is True and replay_entry.get("ok") is True
             and bool(command) and bool(session_id))
    if ready:
        rpg_result = submitter({"session_id": session_id, "command_text": command, "input": command,
                                "context_hash": context_hash, "canonical_path": "rpg_turn_execute"})
        ok = rpg_result.get("ok") is True or rpg_result.get("success") is True
        result: dict[str, Any] = {"ok": ok, "rpg_result": rpg_result, "state_changed": ok}
    else:
        result = {"ok": False, "error": "packet_not_ready", "state_changed": False}
    return {
        "ok": result["ok"],
        "source": "hermes_rpg_approved_flow",
        "session_id": session_id,
        "context_hash": context_hash,
        "command_text": command,
        "ready_for_rpg_pipeline": ready,
        "result": result,
        "state_changed": result.get("state_changed") is True,
    }


def _readout(flow: dict[str, Any]) -> dict[str, Any]:
    result = flow["result"]
    if flow["ok"]:
        error = "none"
    elif not flow["ready_for_rpg_pipeline"]:
        error = "packet_not_ready"
    else:
        error = str(result.get("error") or safe_dict(result.get("rpg_result")).get("error") or "rpg_result_not_ok")
    status = "accepted" if flow["ok"] else "blocked"
    return {
        "ok": flow["ok"],
        "source": "hermes_rpg_flow_readout",
        "status": status,
        "summary": f"Hermes RPG command {status}",
        "session_id": flow["session_id"],
        "context_hash": flow["context_hash"],
        "command_text": flow["command_text"],
        "rpg_ok": flow["ok"],
        "error": error,
        "state_changed": flow["state_changed"],
    }


__all__ = ["RpgSubmitter", "run_approved_command"]
