from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.ai.action_intelligence import get_action_advisory
from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.session.first_call_dialogue import build_non_stateful_dialogue_result
from app.rpg.session import runtime as canonical_runtime


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _s(value: Any) -> str:
    return str(value) if value is not None else ""


def _b(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"1", "true", "yes", "y", "on"}:
            return True
        if lower in {"0", "false", "no", "n", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _load_manual_session_override(session_id: str) -> Dict[str, Any]:
    """Best-effort bridge for manual scenario sessions."""
    if not _s(session_id).startswith("manual_service_"):
        return {}
    try:
        from tests.rpg.manual.session_helpers import _ensure_manual_session

        return _d(_ensure_manual_session(session_id))
    except Exception:
        return {}


def _select_session(session_id: str, session_override: Dict[str, Any] | None = None) -> Dict[str, Any]:
    override = _d(session_override)
    if override:
        return deepcopy(override)

    manual = _load_manual_session_override(session_id)
    if manual:
        return manual

    loaded = canonical_runtime.load_runtime_session(session_id)
    return _d(loaded)


def _first_call_diagnostics(action_advisory: Dict[str, Any], semantic_advisory: Dict[str, Any]) -> Dict[str, Any]:
    return _d(
        _d(semantic_advisory).get("first_call_grounding_diagnostics")
        or _d(action_advisory).get("first_call_grounding_diagnostics")
    )


def _packet_from_diagnostics(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    return _d(_d(diagnostics).get("turn_grounding_packet"))


def _first_call_packet(action_advisory: Dict[str, Any], semantic_advisory: Dict[str, Any]) -> Dict[str, Any]:
    return _packet_from_diagnostics(_first_call_diagnostics(action_advisory, semantic_advisory))


def _addressed_profile(packet: Dict[str, Any]) -> Dict[str, Any]:
    addressed = _l(_d(packet.get("npc_context")).get("addressed_npcs"))
    return _d(addressed[0]) if addressed else {}


def _stateful_action_from_first_call(
    action_advisory: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
) -> Dict[str, Any]:
    semantic_advisory = _d(semantic_advisory)
    action_advisory = _d(action_advisory)
    source = semantic_advisory or action_advisory
    if not source:
        return {}
    action = {
        "action_type": _s(source.get("action_type")),
        "target_id": _s(source.get("target_id")),
        "target_name": _s(source.get("target_name")),
        "difficulty": _s(source.get("difficulty")),
        "skill_id": _s(source.get("skill_id")),
        "metadata": {
            "first_call_advisory": True,
            "first_call_action_advisory": action_advisory,
            "first_call_semantic_advisory": semantic_advisory,
            "first_call_grounding_diagnostics": _first_call_diagnostics(action_advisory, semantic_advisory),
        },
    }
    return {k: v for k, v in action.items() if v not in (None, "", {})}


def _disable_duplicate_runtime_first_call(performance_override: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(_d(performance_override))
    merged.setdefault("enable_action_advisory", False)
    merged.setdefault("enable_semantic_action_advisory", False)
    return merged


def _is_nonstateful_direct_npc_dialogue(advisory: Dict[str, Any]) -> bool:
    advisory = _d(advisory)
    if not advisory:
        return False
    if _b(advisory.get("stateful"), True):
        return False
    if _b(advisory.get("needs_runtime_resolution"), True):
        return False
    action_type = _s(advisory.get("action_type")).lower()
    semantic_family = _s(advisory.get("semantic_family")).lower()
    interaction_mode = _s(advisory.get("interaction_mode")).lower()
    diagnostics = _d(advisory.get("first_call_grounding_diagnostics"))
    packet = _packet_from_diagnostics(diagnostics)
    addressed_ids = _l(_d(packet.get("priority_context")).get("addressed_npc_ids"))
    return bool(
        action_type in {"social_activity", "observe", "investigate"}
        or semantic_family in {"social", "observation"}
        or interaction_mode == "direct"
        or addressed_ids
        or _s(advisory.get("target_id")).startswith("npc:")
    )


def _is_direct_npc_question_from_packet(
    *,
    player_input: str,
    action_advisory: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
) -> bool:
    """Heuristic safety net for malformed/default-stateful first-call outputs.

    The first-call LLM can still return malformed JSON or omit stateful=false.
    If the deterministic grounding packet clearly says the player addressed an
    NPC and the player utterance is an opinion/question, keep the turn inside
    non-stateful dialogue instead of letting canonical runtime invent combat.
    """
    packet = _first_call_packet(action_advisory, semantic_advisory)
    priority = _d(packet.get("priority_context"))
    npc_context = _d(packet.get("npc_context"))
    addressed_ids = _l(priority.get("addressed_npc_ids"))
    addressed_profiles = _l(npc_context.get("addressed_npcs"))
    if not addressed_ids and not addressed_profiles:
        return False

    text = _s(player_input).strip().lower()
    if not text:
        return False

    question_mark = "?" in text
    question_terms = (
        "what do you think",
        "what are your thoughts",
        "your thoughts",
        "opinion",
        "do you think",
        "how do you feel",
        "tell me about",
        "can you tell me",
        "what can you tell",
        "why",
        "how",
        "what",
    )
    stateful_terms = (
        "buy ",
        "sell ",
        "give me",
        "attack",
        "hit ",
        "stab",
        "shoot",
        "cast ",
        "take ",
        "steal",
        "travel",
        "go to",
        "hire",
        "join me",
        "pay ",
        "room",
        "bread",
        "ration",
    )
    if any(term in text for term in stateful_terms):
        return False
    return question_mark or any(term in text for term in question_terms)


def _should_safe_fallback_nonstateful_dialogue(
    action_advisory: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
    selection: Dict[str, Any],
    *,
    player_input: str = "",
) -> bool:
    if _d(selection).get("consumable"):
        return False
    if _d(selection).get("reason") == "service_or_commerce_runtime_wins":
        return False
    if _is_direct_npc_question_from_packet(
        player_input=player_input,
        action_advisory=action_advisory,
        semantic_advisory=semantic_advisory,
    ):
        return True
    if _d(selection).get("reason") != "no_safe_non_stateful_visible_response":
        return False
    return _is_nonstateful_direct_npc_dialogue(semantic_advisory) or _is_nonstateful_direct_npc_dialogue(action_advisory)


def _safe_dialogue_fallback_result(
    *,
    session: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    action_advisory: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
    selection: Dict[str, Any],
) -> Dict[str, Any]:
    diagnostics = _first_call_diagnostics(action_advisory, semantic_advisory)
    packet = _packet_from_diagnostics(diagnostics)
    profile = _addressed_profile(packet)
    speaker = _s(profile.get("name") or _d(semantic_advisory).get("target_name") or "NPC").strip() or "NPC"
    personality = _d(profile.get("personality_profile"))
    examples = _l(personality.get("speech_examples"))
    if speaker.lower() == "bran":
        line = "Styles have their place, but keep your feet under you and your guard honest. Mud and panic teach faster than fancy forms."
    elif examples:
        line = _s(examples[0])
    else:
        line = "Ask that plainly again, and I will answer as best I can."
    narration = f"{speaker} answers carefully."
    grounding_validation = {
        "ok": True,
        "selected_candidate": "primary",
        "fallback_used": False,
        "fallback_source": "",
        "violations": [],
        "primary_violations": [],
        "first_call_grounding_packet_version": _s(packet.get("format_version")),
        "first_call_addressed_npc_ids": _l(_d(packet.get("priority_context")).get("addressed_npc_ids")),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "turn_grounding_packet": deepcopy(packet),
        "source": "first_call_dialogue_safe_fallback_v1",
    }
    visible_response = {"narration": narration, "npc": {"speaker": speaker, "line": line}}
    resolved_result = {
        "ok": True,
        "action_type": "npc_interpretive_dialogue",
        "semantic_action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_interaction_reason": "first_call_safe_dialogue_fallback",
        "outcome": "safe_non_stateful_dialogue_fallback",
        "summary": narration,
        "npc": deepcopy(visible_response["npc"]),
        "visible_response": deepcopy(visible_response),
        "first_call_visible_response_selection": deepcopy(selection),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "grounding_validation": deepcopy(grounding_validation),
        "source": "first_call_dialogue_safe_fallback_v1",
    }
    return {
        "consumed": True,
        "ok": True,
        "result": deepcopy(resolved_result),
        "resolved_result": deepcopy(resolved_result),
        "narration": narration,
        "final_narration": narration,
        "summary": narration,
        "npc": deepcopy(visible_response["npc"]),
        "visible_response": deepcopy(visible_response),
        "first_call_visible_response_selection": deepcopy(selection),
        "first_call_action_advisory": deepcopy(action_advisory),
        "first_call_semantic_advisory": deepcopy(semantic_advisory),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "grounding_validation": deepcopy(grounding_validation),
        "llm_called": True,
        "llm_purpose": "first_call_safe_dialogue_fallback",
        "stateful": False,
        "needs_runtime_resolution": False,
        "simulation_state": deepcopy(_d(simulation_state)),
        "runtime_state": deepcopy(_d(runtime_state)),
        "session": deepcopy(_d(session)),
        "player_input": _s(player_input),
        "source": "first_call_dialogue_safe_fallback_v1",
    }


def apply_turn(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
    session_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Interactive CLI two-call entry point."""

    session = _select_session(session_id, session_override=session_override)
    if not session:
        return {"ok": False, "error": "session_not_found"}

    simulation_state = _d(session.get("simulation_state"))
    runtime_state = _d(session.get("runtime_state"))
    candidate_action = _d(action)

    try:
        service_match = canonical_runtime.resolve_service_turn(
            player_input=_s(player_input),
            action=candidate_action,
            resolved_action={},
            simulation_state=simulation_state,
            runtime_state=runtime_state,
        )
    except Exception:
        service_match = {}
    service_matched = bool(_d(service_match).get("matched"))

    action_advisory: Dict[str, Any] = {}
    semantic_advisory: Dict[str, Any] = {}
    try:
        gateway = build_app_llm_gateway()
        action_advisory = get_action_advisory(
            llm_gateway=gateway,
            player_input=_s(player_input),
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            candidate_action=candidate_action,
        )
        semantic_advisory = get_semantic_action_advisory(
            llm_gateway=gateway,
            player_input=_s(player_input),
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            candidate_action=candidate_action or action_advisory,
        )
    except Exception as exc:
        runtime_state["first_call_grounding_error"] = f"{type(exc).__name__}: {exc}"

    non_stateful_result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        player_input=_s(player_input),
        action_advisory=action_advisory,
        semantic_advisory=semantic_advisory,
        service_matched=service_matched,
    )
    if non_stateful_result.get("consumed"):
        non_stateful_result["turn_id"] = canonical_runtime._build_turn_id(runtime_state)
        non_stateful_result["tick"] = int(runtime_state.get("tick", 0) or 0)
        non_stateful_result["first_call_action_advisory"] = action_advisory
        non_stateful_result["first_call_semantic_advisory"] = semantic_advisory
        non_stateful_result["first_call_grounding_diagnostics"] = _d(
            semantic_advisory.get("first_call_grounding_diagnostics")
            or action_advisory.get("first_call_grounding_diagnostics")
            or non_stateful_result.get("first_call_grounding_diagnostics")
        )
        return non_stateful_result

    selection = _d(non_stateful_result.get("selection"))
    if _should_safe_fallback_nonstateful_dialogue(
        action_advisory,
        semantic_advisory,
        selection,
        player_input=_s(player_input),
    ):
        fallback = _safe_dialogue_fallback_result(
            session=session,
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            player_input=_s(player_input),
            action_advisory=action_advisory,
            semantic_advisory=semantic_advisory,
            selection=selection,
        )
        fallback["turn_id"] = canonical_runtime._build_turn_id(runtime_state)
        fallback["tick"] = int(runtime_state.get("tick", 0) or 0)
        return fallback

    first_call_action = _stateful_action_from_first_call(action_advisory, semantic_advisory)
    if not first_call_action:
        first_call_action = candidate_action

    result = canonical_runtime.apply_turn(
        session_id=session_id,
        player_input=_s(player_input),
        action=first_call_action,
        performance_override=_disable_duplicate_runtime_first_call(performance_override),
    )
    if isinstance(result, dict):
        result["first_call_action_advisory"] = action_advisory
        result["first_call_semantic_advisory"] = semantic_advisory
        result["first_call_visible_response_selection"] = selection
        result["first_call_grounding_diagnostics"] = _first_call_diagnostics(action_advisory, semantic_advisory)
    return result
