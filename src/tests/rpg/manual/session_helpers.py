from __future__ import annotations

import json
import threading
from typing import Any, Dict

from tests.rpg.manual.constants import RPG_SESSION_DIRS
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
    """Load or create a usable manual RPG session.

    The manual harness creates synthetic per-scenario session ids such as
    ``manual_service_spatial_closed_door_blocks_movement_<run_id>``.  The old
    monolith guaranteed that those ids were materialized before scenario setup
    and currency seeding.  The refactor must preserve that behavior: callers
    should never receive ``{}`` for a valid manual session id.
    """
    session_id = str(session_id or "").strip()
    if not session_id:
        raise ValueError("manual_session_id_required")

    session = _load_manual_session_for_test(session_id)
    if isinstance(session, dict) and session:
        session.setdefault("session_id", session_id)
        session.setdefault("id", session_id)
        session.setdefault("runtime_state", {})
        _save_manual_session_for_test(session_id, session)
        return session

    # Prefer existing app/session creation APIs if they are available in this
    # checkout.  These imports are intentionally local so the manual harness can
    # still run in partial test environments.
    created: Dict[str, Any] = {}
    creation_errors: list[str] = []

    for module_name, function_names in [
        (
            "app.rpg.session.service",
            (
                "create_session",
                "start_session",
                "create_new_session",
                "new_session",
            ),
        ),
        (
            "app.rpg.session.runtime",
            (
                "create_session",
                "start_session",
                "create_new_session",
                "new_session",
            ),
        ),
    ]:
        try:
            module = __import__(module_name, fromlist=list(function_names))
        except Exception as exc:
            creation_errors.append(f"{module_name}:import:{type(exc).__name__}:{exc}")
            continue

        for function_name in function_names:
            factory = getattr(module, function_name, None)
            if not callable(factory):
                continue

            for kwargs in (
                {"session_id": session_id},
                {"id": session_id},
                {},
            ):
                try:
                    maybe_session = factory(**kwargs)
                except TypeError:
                    continue
                except Exception as exc:
                    creation_errors.append(
                        f"{module_name}.{function_name}:{type(exc).__name__}:{exc}"
                    )
                    continue

                if isinstance(maybe_session, dict) and maybe_session:
                    created = maybe_session
                    break
            if created:
                break
        if created:
            break

    if not created:
        # Manual-harness fallback.  Keep this compact and explicit; production
        # game runtime remains authoritative for actual gameplay sessions.
        created = {
            "session_id": session_id,
            "id": session_id,
            "simulation_state": {},
            "runtime_state": {},
            "setup_payload": {
                "metadata": {
                    "simulation_state": {},
                }
            },
            "manual_test_session": True,
            "manual_session_creation_errors": creation_errors[:20],
        }

    created = _sanitize_manual_session_for_test(created)
    created.setdefault("session_id", session_id)
    created.setdefault("id", session_id)
    created.setdefault("runtime_state", {})
    _ensure_manual_simulation_roots(created)
    _save_manual_session_for_test(session_id, created)

    reloaded = _load_manual_session_for_test(session_id)
    if isinstance(reloaded, dict) and reloaded:
        reloaded = _sanitize_manual_session_for_test(reloaded)
        reloaded.setdefault("session_id", session_id)
        reloaded.setdefault("id", session_id)
        reloaded.setdefault("runtime_state", {})
        _ensure_manual_simulation_roots(reloaded)
        return reloaded

    return created


def _seed_session_currency(session_id: str, currency: Dict[str, Any]) -> bool:
    session = _ensure_manual_session(session_id)
    if not session:
        raise RuntimeError(f"Failed to ensure manual session for {session_id}")

    session = _sanitize_manual_session_for_test(
        session,
        currency=currency,
        reset_player_items=True,
    )

    try:
        from app.rpg.session.service import save_session
        save_session(session)
    except Exception as exc:
        raise RuntimeError(f"Failed to save session for {session_id}") from exc
    return True


def _load_manual_session_for_test(session_id: str) -> Dict[str, Any]:
    """Load a manual session from the fallback files."""
    session_id = str(session_id or "").strip()
    if not session_id:
        return {}

    # File load for manual tests.
    for root in RPG_SESSION_DIRS:
        if not root.exists():
            continue
        for name in (
            f"{session_id}.json",
            f"{session_id}.rpg.json",
            f"{session_id}.session.json",
        ):
            candidate = root / name
            if candidate.exists() and candidate.is_file():
                try:
                    loaded = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        wrapped_session = loaded.get("session")
                        if isinstance(wrapped_session, dict):
                            return wrapped_session
                        return loaded
                except Exception:
                    continue

    return {}


def _clone_or_create_manual_session(session_id: str) -> Dict[str, Any]:
    """Create or load a manual scenario session."""
    return _load_manual_session_for_test(session_id)


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
    _sync_manual_simulation_state(session)

    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state["tick"] = 0
    runtime_state["turn_history"] = []
    runtime_state["last_turn_contract"] = {}
    runtime_state["last_turn_result"] = {}
    runtime_state["last_narration"] = ""
    runtime_state["last_turn_narration"] = ""
    session["runtime_state"] = runtime_state
    return session


def _sync_manual_simulation_state(session: Dict[str, Any]) -> None:
    simulation_state = _ensure_manual_simulation_roots(session)
    setup_payload = session.setdefault("setup_payload", {})
    metadata = setup_payload.setdefault("metadata", {})
    metadata_simulation_state = metadata.setdefault("simulation_state", {})
    metadata_simulation_state.update(simulation_state)


def _save_manual_session_for_test(session_id: str, session: Dict[str, Any]) -> None:
    """Persist a manual session using the available project save path.

    This helper must not call undefined compatibility shims.  If the app-level
    save helper exists, use it.  Otherwise, write to the manual session file
    location used by the test harness.
    """
    session_id = str(session_id or "").strip()
    if not session_id:
        raise ValueError("manual_session_id_required")

    if not isinstance(session, dict):
        raise TypeError("manual_session_must_be_dict")

    session.setdefault("session_id", session_id)
    session.setdefault("id", session_id)

    # Fallback file persistence for manual tests.  RPG_SESSION_DIRS is already
    # the harness-approved session storage list.
    target_dir = RPG_SESSION_DIRS[0]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{session_id}.json"
    target_path.write_text(
        json.dumps(session, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _manual_apply_interaction_seed_fields(session: Dict[str, Any], setup_interaction_state: Dict[str, Any]) -> Dict[str, Any]:
    return session


def _manual_apply_social_seed_fields(session: Dict[str, Any], setup_interaction_state: Dict[str, Any]) -> Dict[str, Any]:
    return session


def _ensure_manual_simulation_roots(session: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(session, dict):
        raise TypeError("manual_session_must_be_dict")

    simulation_state = session.get("simulation_state")
    if not isinstance(simulation_state, dict):
        simulation_state = {}
        session["simulation_state"] = simulation_state

    runtime_state = session.get("runtime_state")
    if not isinstance(runtime_state, dict):
        session["runtime_state"] = {}

    setup_payload = session.get("setup_payload")
    if not isinstance(setup_payload, dict):
        setup_payload = {}
        session["setup_payload"] = setup_payload

    metadata = setup_payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        setup_payload["metadata"] = metadata

    metadata_simulation_state = metadata.get("simulation_state")
    if not isinstance(metadata_simulation_state, dict):
        metadata_simulation_state = {}
        metadata["simulation_state"] = metadata_simulation_state

    # Keep metadata path and authoritative simulation_state path aligned for
    # manual setup code that reads either one.
    if simulation_state:
        metadata_simulation_state.update(simulation_state)
    if metadata_simulation_state:
        simulation_state.update(metadata_simulation_state)

    return simulation_state


def _default_manual_currency() -> Dict[str, int]:
    return {"gold": 0, "silver": 0, "copper": 0}
