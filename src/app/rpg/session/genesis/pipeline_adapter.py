"""Genesis compiler/bootstrap pipeline adapter for v2 launches."""

from __future__ import annotations

from typing import Any

from .bootstrap import bootstrap_session_from_compiled_genesis
from .compiler import compile_campaign_genesis
from .contract import CampaignGenesisContract
from .legacy_adapter import (
    adapt_genesis_payload_to_new_game_payload,
    attach_genesis_to_created_session,
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def attach_compiled_genesis_to_session(
    result: dict[str, Any],
    compiled: dict[str, Any],
    bootstrap: dict[str, Any],
) -> dict[str, Any]:
    if result.get("ok") is not True:
        return result
    session_id = str(result.get("session_id") or "")
    if not session_id:
        return result
    from app.rpg.session.service import load_session, save_session

    session = load_session(session_id)
    if not session:
        return result
    state = _safe_dict(session.get("state"))
    metadata = _safe_dict(state.get("metadata"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    setup_payload = _safe_dict(session.get("setup_payload"))
    manifest = _safe_dict(session.get("manifest"))

    state["compiled_genesis_snapshot"] = dict(compiled)
    state["bootstrap_snapshot"] = dict(bootstrap)
    state["active_goals"] = list(bootstrap.get("active_goals") or [])
    state["decision_biases"] = dict(bootstrap.get("decision_biases") or {})
    state["world_traits"] = list(bootstrap.get("world_traits") or [])
    metadata["compiler_version"] = compiled.get("compiler_version")
    state["metadata"] = metadata
    setup_payload["compiled_genesis"] = dict(compiled)
    setup_payload["bootstrap_snapshot"] = dict(bootstrap)
    runtime_state["compiled_genesis_snapshot"] = dict(compiled)
    runtime_state["bootstrap_snapshot"] = dict(bootstrap)
    manifest["compiler_version"] = compiled.get("compiler_version")
    session.update(
        {
            "state": state,
            "setup_payload": setup_payload,
            "runtime_state": runtime_state,
            "manifest": manifest,
        }
    )
    saved = save_session(session, compact=False)
    return {
        **result,
        "session": saved,
        "game": saved.get("state", result.get("game", {})),
    }


def create_new_game_from_genesis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _safe_dict(payload.get("request") or payload)
    contract = CampaignGenesisContract.model_validate(raw.get("genesis") or raw)
    legacy = adapt_genesis_payload_to_new_game_payload(
        {"request": {"genesis": contract.model_dump(mode="json")}}
    )
    compiled = compile_campaign_genesis(contract)
    bootstrap = bootstrap_session_from_compiled_genesis(compiled)

    from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session

    result = create_new_game_session(RpgNewGameRequest.model_validate(legacy))
    result = attach_genesis_to_created_session(result, contract)
    return attach_compiled_genesis_to_session(result, compiled, bootstrap)
