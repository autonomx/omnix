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


def _narration_mode(performance_override: Dict[str, Any] | None, runtime_state: Dict[str, Any]) -> str:
    perf = _d(performance_override)
    runtime_state = _d(runtime_state)
    settings = _d(runtime_state.get("runtime_settings") or runtime_state.get("settings"))
    mode = _s(
        perf.get("narration_mode")
        or runtime_state.get("narration_mode")
        or settings.get("narration_mode")
        or "deferred"
    ).strip().lower()
    return mode if mode in {"deferred", "blocking", "deterministic", "disabled"} else "deferred"


def _prepare_stateful_runtime_session(
    session_id: str,
    session: Dict[str, Any],
    *,
    narration_mode: str,
) -> None:
    runtime_state = _d(session.get("runtime_state"))
    runtime_state["narration_mode"] = narration_mode
    runtime_state["force_sync_narration"] = narration_mode == "blocking"
    if narration_mode in {"deferred", "deterministic", "disabled"}:
        runtime_state["deferred_runtime_narration"] = True
    session["runtime_state"] = runtime_state
    try:
        session_to_save = deepcopy(session)
        manifest = _d(session_to_save.get("manifest"))
        manifest["session_id"] = session_id
        manifest.setdefault("id", session_id)
        session_to_save["manifest"] = manifest
        canonical_runtime.save_runtime_session(session_to_save)
        loaded = canonical_runtime.load_runtime_session(session_id)
        if isinstance(loaded, dict):
            loaded_runtime = _d(loaded.get("runtime_state"))
            loaded_runtime["narration_mode"] = narration_mode
            loaded_runtime["force_sync_narration"] = narration_mode == "blocking"
            if narration_mode in {"deferred", "deterministic", "disabled"}:
                loaded_runtime["deferred_runtime_narration"] = True
            loaded["runtime_state"] = loaded_runtime
            canonical_runtime.save_runtime_session(loaded)
    except Exception:
        return


def _stateful_runtime_performance_override(
    performance_override: Dict[str, Any] | None,
    *,
    narration_mode: str,
) -> Dict[str, Any]:
    merged = _disable_duplicate_runtime_first_call(performance_override)
    merged["narration_mode"] = narration_mode
    if narration_mode in {"deterministic", "disabled"}:
        merged["enable_live_narration_llm"] = False
    return merged


def _deterministic_narration_from_result(result: Dict[str, Any]) -> str:
    result = _d(result)
    nested = _d(result.get("result"))
    authoritative = _d(result.get("authoritative"))
    for source in (result, nested, authoritative):
        for key in ("deterministic_fallback_narration", "narration", "final_narration", "summary"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                text = "\n\n".join(_s(item).strip() for item in value if _s(item).strip()).strip()
                if text:
                    return text
    return ""


def _apply_stateful_narration_contract(
    result: Dict[str, Any],
    *,
    narration_mode: str,
    action_advisory: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
    selection: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    nested = _d(result.get("result"))
    deterministic = _deterministic_narration_from_result(result)

    if narration_mode == "disabled":
        narration_status = "disabled"
        narration = ""
    elif narration_mode == "deterministic":
        narration_status = "deterministic"
        narration = deterministic
    elif narration_mode == "blocking":
        narration_status = _s(nested.get("narration_status") or result.get("narration_status") or "completed")
        narration = _s(nested.get("narration") or result.get("narration") or deterministic)
    else:
        narration_status = _s(nested.get("narration_status") or result.get("narration_status") or "queued")
        narration = _s(nested.get("narration") or result.get("narration") or deterministic)

    contract = {
        "format_version": "stateful_runtime_narration_contract_v1",
        "narration_mode": narration_mode,
        "stateful_runtime_authoritative": True,
        "first_call_may_resolve_state": False,
        "runtime_resolved_before_narration": True,
        "narration_may_mutate_state": False,
        "narration_status": narration_status,
        "first_call_visible_response_ignored_for_stateful": bool(
            _d(semantic_advisory).get("visible_response") or _d(action_advisory).get("visible_response")
        ),
        "first_call_selection_reason": _s(_d(selection).get("reason")),
        "first_call_grounding_diagnostics": _first_call_diagnostics(action_advisory, semantic_advisory),
    }

    result["stateful_runtime_narration_contract"] = deepcopy(contract)
    result["narration_mode"] = narration_mode
    result["narration_status"] = narration_status
    if narration_mode in {"disabled", "deterministic"}:
        result["narration"] = narration
        result["final_narration"] = narration
    if nested:
        nested["stateful_runtime_narration_contract"] = deepcopy(contract)
        nested["narration_status"] = narration_status
        if narration_mode in {"disabled", "deterministic"}:
            nested["narration"] = narration
            nested["raw_llm_narrative"] = ""
            nested["used_llm"] = False
        result["result"] = nested
    return result


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
        "sell my",
        "sell this",
        "sell the",
        "sell a ",
        "sell an ",
        "sell you",
        "give me",
        "give ",
        "lend ",
        "borrow",
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
        "come with me",
        "follow me",
        "pay ",
        "discount",
        "cheaper",
        "lower the price",
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


def _direct_dialogue_fallback_topic(player_input: str) -> str:
    text = _s(player_input).lower()
    topic_terms = (
        (
            "commerce_inquiry",
            (
                "food",
                "eat",
                "meal",
                "stew",
                "drink",
                "ale",
                "menu",
                "wares",
                "stock",
                "offer",
                "sell",
                "price",
                "cost",
                "lodging",
                "room",
            ),
        ),
        (
            "rumor_inquiry",
            (
                "rumor",
                "rumour",
                "heard",
                "news",
                "gossip",
                "talk around",
                "word is",
            ),
        ),
        (
            "combat_advice",
            (
                "sword",
                "blade",
                "combat",
                "fight",
                "fighting",
                "guard",
                "stance",
                "style",
                "shield",
                "parry",
            ),
        ),
        (
            "local_knowledge",
            (
                "road",
                "roads",
                "bandit",
                "bandits",
                "caravan",
                "caravans",
                "where",
                "who",
                "what can you tell",
                "tell me about",
            ),
        ),
    )
    for topic, terms in topic_terms:
        if any(term in text for term in terms):
            return topic
    return "general_dialogue"


def _safe_dialogue_fallback_line(
    *,
    speaker: str,
    profile: Dict[str, Any],
    player_input: str,
) -> tuple[str, str]:
    topic = _direct_dialogue_fallback_topic(player_input)
    personality = _d(profile.get("personality_profile"))
    examples = _l(personality.get("speech_examples"))
    speaker_is_bran = speaker.lower() == "bran"

    if topic == "commerce_inquiry":
        if speaker_is_bran:
            return (
                "commerce_inquiry",
                "Food and drink here are simple traveler fare. I can talk through what is usually on hand, "
                "but exact stock and prices need checking at the bar.",
            )
        return (
            "commerce_inquiry",
            "I can talk through what is usually available, but exact stock and prices need checking first.",
        )

    if topic == "rumor_inquiry":
        if speaker_is_bran:
            return (
                "rumor_inquiry",
                "Rumors come in with road dust and thirsty travelers. Ask plain what kind you want, "
                "and I will tell you what I have heard.",
            )
        return (
            "rumor_inquiry",
            "I hear pieces of news, but ask plainly what kind of rumor you want.",
        )

    if topic == "combat_advice" and speaker_is_bran:
        return (
            "combat_advice",
            "Styles have their place, but keep your feet under you and your guard honest. "
            "Mud and panic teach faster than fancy forms.",
        )

    if topic == "local_knowledge" and speaker_is_bran:
        return (
            "local_knowledge",
            "I know the old road, caravan habits, and the kind of trouble that waits where the lamps run out. "
            "Ask me something I have seen, and I will answer straight.",
        )

    if examples and topic in {"combat_advice", "general_dialogue", "local_knowledge"}:
        example = _s(examples[0]).strip()
        if example:
            return (topic, example)

    return (topic, "Ask that plainly again, and I will answer as best I can.")


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
    fallback_topic, line = _safe_dialogue_fallback_line(
        speaker=speaker,
        profile=profile,
        player_input=player_input,
    )
    narration = f"{speaker} answers carefully."
    grounding_validation = {
        "ok": True,
        "selected_candidate": "primary",
        "fallback_topic": fallback_topic,
        "fallback_used": True,
        "fallback_source": "first_call_dialogue_safe_fallback_v1",
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
        "fallback_topic": fallback_topic,
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

    narration_mode = _narration_mode(performance_override, runtime_state)
    _prepare_stateful_runtime_session(session_id, session, narration_mode=narration_mode)

    result = canonical_runtime.apply_turn(
        session_id=session_id,
        player_input=_s(player_input),
        action=first_call_action,
        performance_override=_stateful_runtime_performance_override(
            performance_override,
            narration_mode=narration_mode,
        ),
    )
    if isinstance(result, dict):
        result["first_call_action_advisory"] = action_advisory
        result["first_call_semantic_advisory"] = semantic_advisory
        result["first_call_visible_response_selection"] = selection
        result["first_call_grounding_diagnostics"] = _first_call_diagnostics(action_advisory, semantic_advisory)
        result = _apply_stateful_narration_contract(
            result,
            narration_mode=narration_mode,
            action_advisory=action_advisory,
            semantic_advisory=semantic_advisory,
            selection=selection,
        )
    return result
