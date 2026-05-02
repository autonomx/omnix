from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any, Dict

from tests.rpg.manual.safe import _safe_dict, _safe_str

# From manual_llm_transcript_old.py


def _thread_label() -> str:
    current = threading.current_thread()
    return f"{current.name}:{current.ident}"


def _manual_service_session_id(scenario_name: str, run_id: str, *, stable: bool = False) -> str:
    base = f"manual_service_{scenario_name}"
    if stable:
        return base
    return f"{base}_{run_id}"


def _reset_manual_session_artifacts(session_id: str) -> None:
    """Best-effort delete of saved session artifacts before a manual scenario.

    The normal/default path uses unique run-scoped IDs, so this is mostly for
    --stable-session-ids runs and for local cleanup safety.
    """
    session_id = str(session_id or "").strip()
    if not session_id:
        return

    candidate_names = {
        f"{session_id}.json",
        f"{session_id}.rpg.json",
        f"{session_id}.session.json",
    }

    from pathlib import Path

    REPO_ROOT = Path(__file__).resolve().parents[3]
    RPG_SESSION_DIRS = [
        REPO_ROOT / "resources" / "data" / "rpg_sessions",
        REPO_ROOT / "data" / "rpg_sessions",
    ]

    for root in RPG_SESSION_DIRS:
        if not root.exists():
            continue
        for name in candidate_names:
            candidate = root / name
            if candidate.exists() and candidate.is_file():
                try:
                    candidate.unlink()
                    print(f"[manual][session] reset saved session artifact: {candidate}", flush=True)
                except Exception as exc:
                    print(
                        f"[manual][session] failed to delete {candidate}: {type(exc).__name__}: {exc}",
                        flush=True,
                    )


def _ensure_manual_session(session_id: str) -> Dict[str, Any]:
    """Ensure a manual scenario session exists before running turns.

    Several focused manual scenarios use unique session IDs. apply_turn(...)
    expects the session to exist, so this helper clones/creates one from the
    manual test template when needed.
    """
    session = _clone_or_create_manual_session(session_id)
    if session:
        return session

    try:
        from app.rpg.session.runtime import apply_turn

        warmup = apply_turn(
            session_id="manual_test_session",
            player_input="I wait",
        )
        template_session = _extract_session(warmup)
        if not template_session:
            return {}

        from app.rpg.session.service import save_session

        cloned = deepcopy(template_session)
        manifest = _safe_dict(cloned.get("manifest"))
        manifest["session_id"] = session_id
        manifest["id"] = f"session:{session_id}"
        manifest["title"] = f"Manual Service Scenario: {session_id}"
        cloned["manifest"] = manifest

        cloned = _sanitize_manual_session_for_test(cloned)
        save_session(cloned)
        return cloned
    except Exception:
        return {}


def _seed_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    session = _ensure_manual_session(session_id)
    if not session:
        return False

    session = _sanitize_manual_session_for_test(
        session,
        currency=currency,
        reset_player_items=True,
    )

    try:
        from app.rpg.session.service import save_session
        save_session(session)
    except Exception:
        return False
    return True


def _clone_or_create_manual_session(session_id: str) -> Dict[str, Any]:
    """Create or load a manual scenario session."""
    try:
        from app.rpg.session.service import load_session
        session = _safe_dict(load_session(session_id))
        if session:
            return session
    except Exception:
        pass
    return {}


def _extract_session(result: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(
        result.get("session")
        or _safe_dict(result.get("result")).get("session")
    )


def _sanitize_manual_simulation_state_for_test(
    simulation_state: Dict[str, Any],
    *,
    currency: Dict[str, Any] = None,
    reset_player_items: bool = True,
) -> Dict[str, Any]:
    """Remove accumulated living-world/test state from cloned manual sessions.

    The template session may be dirty from previous manual transcript runs.
    Run-scoped session ids prevent file collisions, but they do not prevent
    cloned simulation_state roots from carrying old transaction history,
    memories, journal entries, stock depletion, world events, active services,
    and relationship/emotion data.
    """
    simulation_state = _safe_dict(simulation_state)

    # Runtime/system roots that must start clean for deterministic scenarios.
    simulation_state["transaction_history"] = []
    simulation_state["active_services"] = []
    simulation_state["memory_rumors"] = []
    simulation_state["relationship_state"] = {}
    simulation_state["npc_emotion_state"] = {}
    simulation_state["service_offer_state"] = {}
    simulation_state["journal_state"] = {"entries": []}
    simulation_state["world_event_state"] = {"events": []}

    simulation_state["memory_state"] = {
        "service_memories": [],
        "social_memories": [],
        "npc_memories": {},
        "npc_memories_flat": [],
        "rumors": [],
    }

    # Keep broad scene/location context, but normalize player inventory.
    player_state = _safe_dict(simulation_state.get("player_state"))
    if not player_state:
        player_state = {}
        simulation_state["player_state"] = player_state

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    if not inventory_state:
        inventory_state = {}
        player_state["inventory_state"] = inventory_state

    if reset_player_items:
        inventory_state["items"] = []
        inventory_state["equipment"] = {}
        inventory_state["last_loot"] = []

    inventory_state.setdefault("capacity", 50)
    inventory_state["currency"] = {
        "gold": int(_safe_dict(currency or _default_manual_currency()).get("gold") or 0),
        "silver": int(_safe_dict(currency or _default_manual_currency()).get("silver") or 0),
        "copper": int(_safe_dict(currency or _default_manual_currency()).get("copper") or 0),
    }

    # Keep location coherent if either root exists.
    location_id = (
        _safe_str(simulation_state.get("location_id"))
        or _safe_str(simulation_state.get("current_location_id"))
        or _safe_str(player_state.get("location_id"))
        or _safe_str(player_state.get("current_location_id"))
    )
    if location_id:
        simulation_state["location_id"] = location_id
        simulation_state["current_location_id"] = location_id
        player_state["location_id"] = location_id
        player_state["current_location_id"] = location_id

    return simulation_state


def _sanitize_manual_session_for_test(session: Dict[str, Any], *, currency: Dict[str, Any] = None, reset_player_items: bool = False) -> Dict[str, Any]:
    session = _safe_dict(session)
    simulation_state = _ensure_manual_simulation_roots(session)
    _sanitize_manual_simulation_state_for_test(
        simulation_state,
        currency=currency,
        reset_player_items=reset_player_items,
    )
    _sync_manual_simulation_state(session, simulation_state)

    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state["tick"] = 0
    runtime_state["turn_history"] = []
    runtime_state["last_turn_contract"] = {}
    runtime_state["last_turn_result"] = {}
    runtime_state["last_narration"] = ""
    runtime_state["last_turn_narration"] = ""
    session["runtime_state"] = runtime_state
    return session


def _sync_manual_simulation_state(session: Dict[str, Any], simulation_state: Dict[str, Any]) -> None:
    setup_payload = _safe_dict(session.get("setup_payload"))
    if not setup_payload:
        setup_payload = {}
        session["setup_payload"] = setup_payload

    metadata = _safe_dict(setup_payload.get("metadata"))
    if not metadata:
        metadata = {}

    session["simulation_state"] = simulation_state
    metadata["simulation_state"] = simulation_state
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload


def _save_manual_session_for_test(session: Dict[str, Any], reason: str = "") -> None:
    try:
        from app.rpg.session.service import save_session

        save_session(session)
    except Exception as exc:
        print(
            f"[manual][session] failed to save manual session"
            f"{f' after {reason}' if reason else ''}: {type(exc).__name__}: {exc}",
            flush=True,
        )


def _manual_apply_interaction_seed_fields(session: Dict[str, Any], setup_interaction_state: Dict[str, Any]) -> Dict[str, Any]:
    return session


def _manual_apply_social_seed_fields(session: Dict[str, Any], setup_interaction_state: Dict[str, Any]) -> Dict[str, Any]:
    return session


def _ensure_manual_simulation_roots(session: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(session.get("simulation_state"))
    if not simulation_state:
        simulation_state = {}
        session["simulation_state"] = simulation_state
        _sync_manual_simulation_state(session, simulation_state)
    return simulation_state


def _default_manual_currency() -> Dict[str, int]:
    return {"gold": 0, "silver": 0, "copper": 0}