from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.economy.service_resolver import resolve_service_turn


def safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _find_actor(simulation_state: Dict[str, Any], target_id: str) -> Dict[str, Any]:
    target_id = safe_str(target_id)
    for key in ("actor_states", "npc_states", "npcs", "actors"):
        for row in safe_list(simulation_state.get(key)):
            row = safe_dict(row)
            if safe_str(row.get("id")) == target_id:
                return row
    return {}


def _guess_target_id(simulation_state: Dict[str, Any], text: str, action: Dict[str, Any]) -> str:
    explicit = safe_str(action.get("target_id") or action.get("target"))
    if (
        explicit
        and explicit not in {"room", "inn", "service", "player"}
        and not explicit.startswith("npc:")
        and not explicit.startswith("npc_")
        and not explicit.startswith("np:")
    ):
        return explicit

    text_l = text.lower()
    for key in ("actor_states", "npc_states", "npcs", "actors"):
        for row in safe_list(simulation_state.get(key)):
            row = safe_dict(row)
            actor_id = safe_str(row.get("id"))
            name = safe_str(row.get("name") or row.get("display_name") or actor_id)
            if actor_id and (actor_id.lower() in text_l or name.lower() in text_l):
                return actor_id

    # Fallback for common names if not found in state
    if "bran" in text_l:
        return "Bran"

    return ""


def interpret_turn_action(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    action: Dict[str, Any],
) -> Dict[str, Any]:
    text = safe_str(player_input)
    text_l = text.lower()
    action = safe_dict(action)

    action_type = safe_str(action.get("action_type") or "unknown")
    target_id = _guess_target_id(simulation_state, text, action)
    if (
        target_id == "player"
        or target_id.startswith("npc:")
        or target_id.startswith("npc_")
        or target_id.startswith("np:")
    ):
        target_id = ""
    target = _find_actor(simulation_state, target_id)
    target_name = safe_str(target.get("name") or target.get("display_name") or target_id)

    hostile_words = ("punch", "kick", "hit", "strike", "throw", "slam", "shove", "attack", "stab", "shoot")
    apology_words = ("sorry", "apologize", "apologise", "forgive", "make amends")
    question_words = ("ask", "how", "what", "why", "where", "when", "who")
    performance_words = ("dance", "sing", "perform", "juggle", "play music")
    service_words = (
        "room",
        "rent",
        "inn",
        "bed",
        "stay",
        "lodging",
        "accommodation",
        "price",
        "cost",
        "buy",
        "purchase",
        "sell",
        "sells",
        "shop",
        "goods",
        "food",
        "meal",
        "drink",
        "ale",
        "rumor",
        "rumour",
        "information",
        "repair",
        "train",
        "transport",
    )

    intent = action_type
    if any(w in text_l for w in hostile_words):
        intent = "attack"
    elif any(w in text_l for w in apology_words):
        intent = "apologize"
    elif any(w in text_l for w in service_words):
        intent = "service"
    elif "?" in text_l or any(w in text_l for w in question_words):
        intent = "ask"
    elif any(w in text_l for w in performance_words):
        intent = "perform"

    return {
        "intent": intent,
        "raw_input": text,
        "action_type": action_type,
        "verb": action_type,
        "target_id": target_id,
        "target_name": target_name,
        "style": action.get("style") or "",
        "force": "high" if any(w in text_l for w in ("throw", "slam", "kick")) else "moderate",
        "confidence": action.get("confidence", 0.75),
        "source": "turn_contract_v1",
    }


def derive_state_delta(
    simulation_state: Dict[str, Any],
    interpreted_action: Dict[str, Any],
    resolved_action: Dict[str, Any],
) -> Dict[str, Any]:
    intent = safe_str(interpreted_action.get("intent"))
    target_id = safe_str(interpreted_action.get("target_id"))
    target_name = safe_str(interpreted_action.get("target_name") or target_id)

    delta = {
        "npc_updates": [],
        "scene_updates": {},
        "flags": [],
        "memories": [],
    }

    if intent == "attack" and target_id:
        delta["npc_updates"].append(
            {
                "id": target_id,
                "mood": "angry",
                "activity": "recovering from the player's attack",
                "relationship_to_player_delta": -35,
                "trust_delta": -25,
                "fear_delta": 10,
                "health_delta": -4,
                "memory": f"The player attacked {target_name}.",
            }
        )
        delta["scene_updates"]["tension_delta"] = 25
        delta["flags"].append("hostile_action")
        return delta

    if intent == "apologize" and target_id:
        delta["npc_updates"].append(
            {
                "id": target_id,
                "mood": "wary",
                "activity": "listening cautiously",
                "relationship_to_player_delta": 8,
                "trust_delta": 3,
                "memory": f"The player apologized to {target_name}.",
            }
        )
        delta["scene_updates"]["tension_delta"] = -5
        return delta

    if intent == "perform":
        delta["scene_updates"]["attention_delta"] = 10
        delta["flags"].append("performance")
        return delta

    if intent in {"ask", "service"} and target_id:
        delta["npc_updates"].append(
            {
                "id": target_id,
                "activity": "speaking with the player",
                "memory": f"The player asked: {safe_str(interpreted_action.get('raw_input'))}",
            }
        )

    return delta


def apply_state_delta(simulation_state: Dict[str, Any], state_delta: Dict[str, Any]) -> Dict[str, Any]:
    state = deepcopy(safe_dict(simulation_state))

    actor_rows = safe_list(state.get("actor_states"))
    if not actor_rows:
        actor_rows = safe_list(state.get("npc_states"))

    actor_rows = [dict(safe_dict(r)) for r in actor_rows]

    for update in safe_list(state_delta.get("npc_updates")):
        update = safe_dict(update)
        actor_id = safe_str(update.get("id"))
        if not actor_id:
            continue

        row = None
        for existing in actor_rows:
            if safe_str(existing.get("id")) == actor_id:
                row = existing
                break

        if row is None:
            row = {"id": actor_id, "name": actor_id}
            actor_rows.append(row)

        if update.get("mood"):
            row["mood"] = safe_str(update.get("mood"))
        if update.get("activity"):
            row["activity"] = safe_str(update.get("activity"))

        row["health"] = max(0, min(100, safe_int(row.get("health"), 100) + safe_int(update.get("health_delta"), 0)))
        row["relationship_to_player"] = max(
            -100,
            min(
                100,
                safe_int(row.get("relationship_to_player"), 0)
                + safe_int(update.get("relationship_to_player_delta"), 0),
            ),
        )
        row["trust"] = max(-100, min(100, safe_int(row.get("trust"), 0) + safe_int(update.get("trust_delta"), 0)))
        row["fear"] = max(0, min(100, safe_int(row.get("fear"), 0) + safe_int(update.get("fear_delta"), 0)))

        memories = safe_list(row.get("recent_memories"))
        memory = safe_str(update.get("memory"))
        if memory:
            memories.append(memory[:220])
            row["recent_memories"] = memories[-8:]

    state["actor_states"] = actor_rows
    if "npc_states" in state:
        state["npc_states"] = [r for r in actor_rows if safe_str(r.get("id")) != "player"]

    scene_updates = safe_dict(state_delta.get("scene_updates"))
    if scene_updates:
        scene_state = safe_dict(state.get("scene_state"))
        if "tension_delta" in scene_updates:
            scene_state["tension"] = max(
                0,
                min(100, safe_int(scene_state.get("tension"), 0) + safe_int(scene_updates.get("tension_delta"), 0)),
            )
        if "attention_delta" in scene_updates:
            scene_state["attention"] = max(
                0,
                min(100, safe_int(scene_state.get("attention"), 0) + safe_int(scene_updates.get("attention_delta"), 0)),
            )
        state["scene_state"] = scene_state

    return state


def build_narration_brief(
    interpreted_action: Dict[str, Any],
    resolved_action: Dict[str, Any],
    state_delta: Dict[str, Any],
) -> Dict[str, Any]:
    intent = safe_str(interpreted_action.get("intent"))
    target_name = safe_str(interpreted_action.get("target_name"))
    raw_input = safe_str(interpreted_action.get("raw_input"))

    if intent == "attack":
        summary = (
            f"The player takes hostile physical action toward {target_name or 'the target'}: {raw_input}. "
            "Narrate the physical motion, immediate reaction, and social fallout. "
            "The target should react with anger, shock, fear, or defensive hostility according to the state delta."
        )
        tone = "tense"
    elif intent == "apologize":
        summary = (
            f"The player apologizes to {target_name or 'the NPC'}: {raw_input}. "
            "Narrate a cautious emotional response. The apology may soften the moment but does not erase recent harm."
        )
        tone = "wary"
    elif intent == "service":
        service_result = safe_dict(resolved_action.get("service_result"))
        service_kind = safe_str(service_result.get("service_kind"))
        provider_name = safe_str(service_result.get("provider_name") or target_name or "the provider")
        status = safe_str(service_result.get("status"))
        offers = safe_list(service_result.get("offers"))

        if offers:
            offer_labels = [
                safe_str(safe_dict(offer).get("label"))
                for offer in offers
                if safe_str(safe_dict(offer).get("label"))
            ]
            summary = (
                f"The player is making a deterministic service inquiry with {provider_name}: {raw_input}. "
                f"Service kind: {service_kind or 'unknown'}. "
                f"Registered offers: {', '.join(offer_labels)}. "
                "Narration may mention only these registered offers and must not invent payment, purchase completion, inventory changes, rewards, rooms, prices, or services."
            )
        else:
            summary = (
                f"The player is making a deterministic service inquiry with {provider_name}: {raw_input}. "
                f"Service kind: {service_kind or 'unknown'}. "
                f"Service status: {status or 'unknown'}. "
                "No registered offer is available; narration must not invent one."
            )
        tone = "practical"
    elif intent == "ask":
        summary = (
            f"The player asks {target_name or 'someone nearby'}: {raw_input}. "
            "The NPC should answer naturally, using their current mood, memories, and the scene context."
        )
        tone = "conversational"
    elif intent == "perform":
        summary = (
            f"The player performs or behaves expressively: {raw_input}. "
            "Narrate the room's reaction with personality and scene awareness."
        )
        tone = "lively"
    else:
        summary = (
            f"The player attempts: {raw_input}. "
            "Interpret the action generously and narrate a concrete scene-aware result."
        )
        tone = "dramatic"

    return {
        "tone": tone,
        "summary": summary,
        "must_include": safe_list(resolved_action.get("facts")),
        "state_delta": state_delta,
        "creative_freedom": [
            "body language",
            "sensory detail",
            "natural NPC dialogue",
            "pacing",
            "emotional texture",
        ],
        "forbidden": [
            "do not invent rewards",
            "do not invent inventory changes",
            "do not invent completed payment",
            "do not invent major injury beyond state_delta",
            "do not add new NPCs or locations unless already present",
        ],
    }


def supplement_generic_resolved_action(
    resolved_action: Dict[str, Any],
    interpreted_action: Dict[str, Any],
    narration_brief: Dict[str, Any],
) -> Dict[str, Any]:
    resolved = dict(safe_dict(resolved_action))
    generic_values = {"", "you act", "action: you act.", "action: you act", "you act."}

    existing = safe_str(
        resolved.get("narrative_brief")
        or resolved.get("message")
        or resolved.get("summary")
        or resolved.get("result_text")
    ).strip()

    if existing.lower() in generic_values:
        resolved["summary"] = safe_str(narration_brief.get("summary"))
        resolved["message"] = safe_str(narration_brief.get("summary"))
        resolved["narrative_brief"] = safe_str(narration_brief.get("summary"))

    resolved.setdefault("action_type", safe_str(interpreted_action.get("intent") or interpreted_action.get("action_type")))
    resolved.setdefault("outcome", "interpreted_action")
    resolved["turn_contract_managed"] = True
    return resolved


def build_npc_behavior_context(
    simulation_state: Dict[str, Any],
    interpreted_action: Dict[str, Any],
    state_delta: Dict[str, Any],
) -> Dict[str, Any]:
    target_id = safe_str(interpreted_action.get("target_id"))
    if not target_id:
        return {}

    actor = _find_actor(simulation_state, target_id)
    if not actor:
        return {}

    mood = safe_str(actor.get("mood") or "neutral")
    activity = safe_str(actor.get("activity") or "")
    relationship = safe_int(actor.get("relationship_to_player"), 0)
    trust = safe_int(actor.get("trust"), 0)
    fear = safe_int(actor.get("fear"), 0)
    health = safe_int(actor.get("health"), 100)
    memories = safe_list(actor.get("recent_memories"))[-5:]

    reaction_tone = "neutral"
    if mood in {"furious", "hostile", "angry"}:
        reaction_tone = "hostile"
    elif relationship <= -50:
        reaction_tone = "hostile"
    elif relationship <= -20 or trust < -10:
        reaction_tone = "wary"
    elif fear >= 30:
        reaction_tone = "afraid"
    elif relationship >= 30 or trust >= 25:
        reaction_tone = "friendly"

    return {
        "target_id": target_id,
        "target_name": safe_str(actor.get("name") or actor.get("display_name") or target_id),
        "mood": mood,
        "activity": activity,
        "relationship_to_player": relationship,
        "trust": trust,
        "fear": fear,
        "health": health,
        "recent_memories": memories,
        "reaction_tone": reaction_tone,
        "state_delta": state_delta,
        "required_reaction": bool(target_id),
    }


def normalize_service_action_contract(
    action: Dict[str, Any],
    resolved_action: Dict[str, Any],
    service_result: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    action = dict(safe_dict(action))
    resolved_action = dict(safe_dict(resolved_action))
    service_result = safe_dict(service_result)

    if not service_result.get("matched"):
        return action, resolved_action

    service_action_type = safe_str(service_result.get("kind") or "service_inquiry")
    provider_id = safe_str(service_result.get("provider_id"))
    provider_name = safe_str(service_result.get("provider_name"))
    service_kind = safe_str(service_result.get("service_kind"))

    action["action_type"] = service_action_type
    action["service_kind"] = service_kind
    action["target_id"] = provider_id
    action["target_name"] = provider_name
    action["provider_id"] = provider_id
    action["provider_name"] = provider_name
    action["source"] = "deterministic_service_resolver"

    metadata = safe_dict(action.get("metadata"))
    metadata["service_result"] = service_result
    metadata["service_kind"] = service_kind
    metadata["service_status"] = safe_str(service_result.get("status"))
    action["metadata"] = metadata

    resolved_action["action_type"] = service_action_type
    resolved_action["service_kind"] = service_kind
    resolved_action["target_id"] = provider_id
    resolved_action["target_name"] = provider_name
    resolved_action["service_result"] = service_result

    action_metadata = safe_dict(resolved_action.get("action_metadata"))
    action_metadata["transaction_kind"] = service_action_type
    action_metadata["service_kind"] = service_kind
    action_metadata["provider_id"] = provider_id
    action_metadata["provider_name"] = provider_name
    action_metadata["price_source"] = (
        "deterministic_service_registry"
        if safe_list(service_result.get("offers"))
        else ""
    )
    resolved_action["action_metadata"] = action_metadata

    return action, resolved_action


def build_turn_contract(
    *,
    player_input: str,
    action: Dict[str, Any],
    resolved_action: Dict[str, Any],
    simulation_state_before: Dict[str, Any],
    simulation_state_after: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    interpreted = interpret_turn_action(
        simulation_state_before,
        runtime_state,
        player_input,
        action,
    )

    service_result = resolve_service_turn(
        player_input=player_input,
        action=action,
        resolved_action=resolved_action,
        simulation_state=simulation_state_before,
        runtime_state=runtime_state,
    )
    action, resolved_action = normalize_service_action_contract(
        action,
        resolved_action,
        service_result,
    )
    if service_result.get("matched"):
        interpreted["intent"] = "service"
        interpreted["service_kind"] = safe_str(service_result.get("service_kind"))
        interpreted["service_kind_status"] = safe_str(service_result.get("status"))
        interpreted["target_id"] = safe_str(service_result.get("provider_id"))
        interpreted["target_name"] = safe_str(service_result.get("provider_name"))

    resolved_for_contract = dict(safe_dict(resolved_action))
    if service_result.get("matched"):
        resolved_for_contract["service_result"] = service_result

    state_delta = derive_state_delta(
        simulation_state_before,
        interpreted,
        resolved_for_contract,
    )
    narration_brief = build_narration_brief(
        interpreted,
        resolved_for_contract,
        state_delta,
    )
    resolved = supplement_generic_resolved_action(
        resolved_for_contract,
        interpreted,
        narration_brief,
    )

    npc_behavior_context = build_npc_behavior_context(
        simulation_state_after,
        interpreted,
        state_delta,
    )

    return {
        "version": "turn_contract_v1",
        "player_input": player_input,
        "action": action,
        "interpreted_action": interpreted,
        "resolved_action": resolved,
        "resolved_result": resolved,
        "service_result": service_result,
        "state_delta": state_delta,
        "npc_behavior_context": npc_behavior_context,
        "narration_brief": narration_brief,
        "presentation": {
            "available_actions": safe_list(service_result.get("available_actions"))
            if service_result.get("matched")
            else [],
        },
    }