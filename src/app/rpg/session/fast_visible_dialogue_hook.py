"""Fast deterministic visible dialogue path for harmless NPC talk.

The normal interactive runtime still owns gameplay state. This hook only avoids a
foreground semantic-LLM round trip for clearly non-mutating addressed NPC
small-talk where the runtime already has a deterministic safe fallback answer.
"""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
from time import perf_counter
from typing import Any

from app.rpg.session.turn_grounding import build_turn_grounding_packet

_SENTINEL = "_omnix_fast_visible_dialogue_hook_installed"
_SOURCE = "fast_visible_dialogue_v1"
_STATEFUL_TERMS = (
    "attack",
    "buy",
    "sell",
    "trade",
    "pay",
    "hire",
    "join me",
    "come with me",
    "follow me",
    "give me",
    "take ",
    "steal",
    "travel",
    "go to",
    "equip",
    "drop",
    "use ",
    "cast",
)
_DIALOGUE_TERMS = (
    "ask ",
    "say ",
    "tell ",
    "talk ",
    "speak ",
    "how are",
    "how's",
    "how is",
    "who are you",
    "your name",
    "what do you think",
    "opinion",
    "rumor",
    "rumour",
    "gossip",
    "news",
    "heard",
    "word around",
    "word is",
)


def install_fast_visible_dialogue_hook() -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime

    if getattr(runtime, _SENTINEL, False):
        return

    original = runtime.apply_turn

    @wraps(original)
    def patched_apply_turn(
        session_id: str,
        player_input: str,
        action: dict[str, Any] | None = None,
        *,
        performance_override: dict[str, Any] | None = None,
        session_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fast = _try_fast_visible_dialogue(
            runtime,
            session_id=session_id,
            player_input=player_input,
            action=action,
            performance_override=performance_override,
            session_override=session_override,
        )
        if fast:
            return fast
        return original(
            session_id,
            player_input,
            action,
            performance_override=performance_override,
            session_override=session_override,
        )

    runtime.apply_turn = patched_apply_turn
    setattr(runtime, _SENTINEL, True)


def _try_fast_visible_dialogue(
    runtime: Any,
    *,
    session_id: str,
    player_input: str,
    action: dict[str, Any] | None,
    performance_override: dict[str, Any] | None,
    session_override: dict[str, Any] | None,
) -> dict[str, Any]:
    start = perf_counter()
    perf = _d(performance_override)
    if perf.get("fast_visible_dialogue") is not True:
        return {}

    text = _s(player_input).strip()
    if not _looks_like_fast_dialogue(text, _d(action)):
        return {}

    session = runtime._select_session(session_id, session_override=session_override)
    if not session:
        return {}

    simulation_state = _d(session.get("simulation_state"))
    runtime_state = _d(session.get("runtime_state"))
    candidate_action = _d(action)
    packet = build_turn_grounding_packet(
        player_input=text,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        candidate_action=candidate_action,
    )
    profile = _first_addressed_profile(packet)
    target_name = _s(profile.get("name") or candidate_action.get("target_name")).strip()
    target_id = _s(profile.get("id") or candidate_action.get("target_id")).strip()
    if not target_name and not target_id:
        return {}

    semantic_advisory = {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "target_id": target_id,
        "target_name": target_name,
        "stateful": False,
        "needs_runtime_resolution": False,
        "direct_response_gate": {
            "safe_to_display_now": False,
            "reason": "fast deterministic safe fallback handles visible dialogue",
            "risk_flags": [],
        },
        "first_call_grounding_diagnostics": {
            "source": _SOURCE,
            "provider_called": False,
            "provider_status": "fast_visible_dialogue_skip",
            "provider_parse_ok": True,
            "raw_text": "",
            "raw_text_length": 0,
            "turn_grounding_packet": deepcopy(packet),
            "format_version": "first_call_grounding_diagnostics_fast_visible_v1",
        },
        "source": _SOURCE,
    }
    selection = {
        "consumable": False,
        "reason": "fast_visible_dialogue_safe_fallback",
        "source": _SOURCE,
    }
    result = runtime._safe_dialogue_fallback_result(
        session=session,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        player_input=text,
        action_advisory={},
        semantic_advisory=semantic_advisory,
        selection=selection,
    )
    result["turn_id"] = runtime.canonical_runtime._build_turn_id(runtime_state)
    result["tick"] = int(runtime_state.get("tick", 0) or 0)
    result["llm_called"] = False
    result["llm_purpose"] = "fast_visible_dialogue_safe_fallback"
    result["fast_visible_dialogue"] = True
    result["source"] = _SOURCE
    nested = _d(result.get("result"))
    if nested:
        nested["llm_called"] = False
        nested["llm_purpose"] = "fast_visible_dialogue_safe_fallback"
        nested["fast_visible_dialogue"] = True
        nested["source"] = _SOURCE
        result["result"] = nested
    timing = {
        "manual_turn_timing_source": _SOURCE,
        "pre_runtime_intent_llm_ms": 0.0,
        "deterministic_runtime_apply_ms": 0.0,
        "grounding_validation_ms": 0.0,
        "repair_ms": 0.0,
        "state_snapshot_ms": 0.0,
        "deferred_enqueue_ms": 0.0,
        "fast_visible_dialogue_ms": round((perf_counter() - start) * 1000.0, 3),
        "manual_turn_ms": round((perf_counter() - start) * 1000.0, 3),
    }
    return runtime._attach_manual_stage_timing(result, timing)


def _looks_like_fast_dialogue(player_input: str, action: dict[str, Any]) -> bool:
    text = player_input.casefold().strip()
    if not text:
        return False
    if action and _s(action.get("action_type")).strip().lower() not in {"", "observe", "social_activity", "talk", "conversation"}:
        return False
    if any(term in text for term in _STATEFUL_TERMS):
        return False
    return "?" in text or any(term in text for term in _DIALOGUE_TERMS)


def _first_addressed_profile(packet: dict[str, Any]) -> dict[str, Any]:
    npc_context = _d(packet.get("npc_context"))
    addressed = npc_context.get("addressed_npcs")
    if isinstance(addressed, list) and addressed:
        return _d(addressed[0])
    by_id = _d(npc_context.get("addressed_npcs_by_id"))
    if by_id:
        npc_id, profile = next(iter(by_id.items()))
        profile = _d(profile)
        profile.setdefault("id", npc_id)
        return profile
    return {}


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    return str(value) if value is not None else ""
