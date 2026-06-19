"""Loadout action wrapper that runs item turn hooks after item mutations.

The direct loadout action owns inventory/equipment mutations and currently saves the
session immediately.  This wrapper keeps the public loadout implementation stable
while giving route and autoplay callers a compact integration point for the item
turn-hook bridge.
"""
from __future__ import annotations

from typing import Any

from app.rpg.session.item_loadout_hooks import run_loadout_item_hooks
from app.rpg.session.loadout import RpgLoadoutActionRequest, apply_loadout_action
from app.rpg.session.service import save_session


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _session_genre(state: dict[str, Any], session: dict[str, Any]) -> str:
    metadata = _safe_dict(state.get("metadata"))
    identity = _safe_dict(state.get("character_identity"))
    setup = _safe_dict(session.get("setup_payload"))
    return str(
        metadata.get("genre")
        or identity.get("genre")
        or setup.get("genre")
        or metadata.get("campaign_template")
        or "classic_fantasy"
    )


def apply_loadout_action_with_item_hooks(
    session_id: str,
    request: RpgLoadoutActionRequest,
    *,
    diagnostics_interval: int = 10,
    maintenance_interval: int = 25,
    report_interval: int = 20,
    objective_limit: int = 5,
    record_trace: bool = True,
    record_hook_trace: bool = True,
) -> dict[str, Any]:
    """Apply a loadout action and run item hooks against successful item actions."""

    result = apply_loadout_action(session_id, request)
    if result.get("ok") is not True:
        return result

    session = _safe_dict(result.get("session"))
    state = _safe_dict(session.get("state") or result.get("game"))
    if not session or not state:
        return result
    session["state"] = state

    hook_result = run_loadout_item_hooks(
        state,
        action=request.action,
        station=request.station,
        genre=_session_genre(state, session),
        diagnostics_interval=diagnostics_interval,
        maintenance_interval=maintenance_interval,
        report_interval=report_interval,
        objective_limit=objective_limit,
        record_trace=record_trace,
        record_hook_trace=record_hook_trace,
    )
    if hook_result.get("skipped"):
        return {**result, "item_hook_result": hook_result}

    saved = save_session(session, compact=False)
    return {
        **result,
        "session": saved,
        "game": _safe_dict(saved.get("state")),
        "item_hook_result": hook_result,
    }
