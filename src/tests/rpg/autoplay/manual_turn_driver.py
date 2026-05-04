from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _ensure_manual_simulation_roots,
    _reset_manual_session_artifacts,
    _save_manual_session_for_test,
)
from tests.rpg.manual.turn_execution import _run_one_manual_turn


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


AUTOPLAY_PRESERVED_SIMULATION_ROOTS = {
    "scene",
    "location",
    "runtime",
    "story_arc_state",
    "story_arc_milestone_state",
    "quest_log_state",
    "campaign_journal_state",
    "story_event_queue_state",
    "story_pack_state",
    "campaign_director_state",
    "lore_state",
    "npc_evolution_state",
    "social_state",
}


def merge_autoplay_simulation_state(
    *,
    before_state: Dict[str, Any],
    returned_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge raw apply_turn state without letting partial state erase campaign roots.

    Some manual/app turn paths return only a compact session simulation_state
    containing memory/presentation roots. Autoplay seeds campaign/objective
    state before the turn, so a partial returned state must be merged over the
    pre-turn state rather than replacing it wholesale.
    """
    before_state = deepcopy(_safe_dict(before_state))
    returned_state = deepcopy(_safe_dict(returned_state))
    merged = deepcopy(before_state)

    for key, value in returned_state.items():
        if key in AUTOPLAY_PRESERVED_SIMULATION_ROOTS:
            if isinstance(value, dict) and value:
                merged[key] = value
            elif key not in merged:
                merged[key] = value
            continue
        merged[key] = value

    for key in AUTOPLAY_PRESERVED_SIMULATION_ROOTS:
        if key in before_state and key not in merged:
            merged[key] = deepcopy(before_state[key])

    return merged


def _save_through_app_session_service(session: Dict[str, Any]) -> None:
    """Best-effort save through the same app service manual setup relies on."""
    try:
        from app.rpg.session.service import save_session

        save_session(session)
    except Exception:
        # _save_manual_session_for_test already wrote the fallback harness file.
        # Some partial test environments do not expose the app save path.
        return


def prepare_autoplay_manual_session(
    *,
    session_id: str,
    simulation_state: Dict[str, Any],
    reset_session_state: bool = True,
) -> Dict[str, Any]:
    """Create the same kind of session manual_llm_transcript.py uses.

    The autoplay runner owns player input selection, but the turn execution
    should be identical to manual scenarios: save a manual session, then call
    the same apply_turn path via _run_one_manual_turn().
    """
    if reset_session_state:
        _reset_manual_session_artifacts(session_id)

    session = _ensure_manual_session(session_id)
    sim = _ensure_manual_simulation_roots(session)
    sim.clear()
    sim.update(deepcopy(_safe_dict(simulation_state)))

    session["simulation_state"] = sim
    session.setdefault("runtime_state", {})
    session.setdefault("setup_payload", {})
    session["setup_payload"].setdefault("metadata", {})
    session["setup_payload"]["metadata"]["simulation_state"] = deepcopy(sim)
    session["manual_autoplay_session"] = True

    _save_manual_session_for_test(session_id, session)
    _save_through_app_session_service(session)
    return _ensure_manual_session(session_id)


def load_autoplay_manual_session(session_id: str) -> Dict[str, Any]:
    return _ensure_manual_session(session_id)


def load_autoplay_simulation_state(session_id: str) -> Dict[str, Any]:
    return _safe_dict(load_autoplay_manual_session(session_id).get("simulation_state"))


def _extract_turn_contract_from_raw_result(raw_result: Dict[str, Any]) -> Dict[str, Any]:
    raw_result = _safe_dict(raw_result)
    return _safe_dict(
        raw_result.get("turn_contract")
        or _safe_dict(raw_result.get("result")).get("turn_contract")
        or _safe_dict(raw_result.get("contract"))
    )


def _extract_simulation_state_from_raw_result(
    raw_result: Dict[str, Any],
    fallback_state: Dict[str, Any],
) -> Dict[str, Any]:
    raw_result = _safe_dict(raw_result)
    candidates = [
        raw_result.get("simulation_state"),
        _safe_dict(raw_result.get("session")).get("simulation_state"),
        _safe_dict(raw_result.get("result")).get("simulation_state"),
        _safe_dict(_safe_dict(raw_result.get("result")).get("session")).get("simulation_state"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return fallback_state


def run_autoplay_manual_turn(
    *,
    session_id: str,
    player_input: str,
    turn_index: int,
    scenario_name: str = "autoplay_campaign",
    target_channel: str = "autoplay_runtime",
    console_llm: bool = False,
    console_llm_raw: bool = False,
    console_llm_max_chars: int = 10_000,
) -> Dict[str, Any]:
    """Run one autoplay turn through the manual harness turn function."""
    turn_summary = _run_one_manual_turn(
        session_id=session_id,
        turn=player_input,
        turn_index=turn_index,
        scenario_name=scenario_name,
        target_channel=target_channel,
        console_llm=console_llm,
        console_llm_raw=console_llm_raw,
        console_llm_max_chars=console_llm_max_chars,
        story_event_queue_checks=None,
        include_raw_result=True,
    )

    before_session = load_autoplay_manual_session(session_id)
    before_state = _safe_dict(before_session.get("simulation_state"))
    after_session = before_session
    fallback_after_state = _safe_dict(after_session.get("simulation_state"))
    raw_result = _safe_dict(turn_summary.get("raw_result"))
    returned_after_state = _extract_simulation_state_from_raw_result(
        raw_result,
        fallback_after_state,
    )
    after_state = merge_autoplay_simulation_state(
        before_state=before_state,
        returned_state=returned_after_state,
    )
    after_session["simulation_state"] = after_state
    after_session.setdefault("setup_payload", {}).setdefault("metadata", {})[
        "simulation_state"
    ] = deepcopy(after_state)
    _save_manual_session_for_test(session_id, after_session)
    _save_through_app_session_service(after_session)
    turn_contract = _safe_dict(
        turn_summary.get("raw_turn_contract")
        or _extract_turn_contract_from_raw_result(raw_result)
    )
    narration = (
        _safe_str(turn_summary.get("raw_narration"))
        or _extract_narration_from_manual_turn_summary(turn_summary)
    )
    return {
        "ok": not bool(turn_summary.get("error")),
        "runtime_name": "manual_harness._run_one_manual_turn",
        "manual_turn_summary": turn_summary,
        "simulation_state": after_state,
        "turn_contract": turn_contract,
        "narration": narration,
        "player_input": player_input,
    }


def _extract_narration_from_manual_turn_summary(turn_summary: Dict[str, Any]) -> str:
    result = _safe_dict(turn_summary.get("result"))
    candidates = [
        result.get("narration"),
        result.get("narrative"),
        result.get("text"),
        result.get("message"),
        result.get("rendered_narration"),
        result.get("deterministic_fallback_narration"),
        _safe_dict(result.get("result")).get("narration"),
        _safe_dict(result.get("session")).get("runtime_state", {}).get("last_narration")
        if isinstance(_safe_dict(result.get("session")).get("runtime_state"), dict)
        else "",
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""