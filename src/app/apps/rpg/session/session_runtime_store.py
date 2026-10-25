from __future__ import annotations


# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _safe_dict as _safe_dict,
    _safe_list as _safe_list,
    _safe_str as _safe_str,
)
import json as json
import ast as ast
from app.apps.rpg.session.narration_queue_runtime import (
    _runtime_compact_save_enabled as _runtime_compact_save_enabled,
)
from app.apps.rpg.session.service import (
    load_session as load_canonical_session,
    save_session as save_canonical_session,
)
from app.apps.rpg.session.semantic_interaction_runtime import (
    _find_npc_target_by_name as _find_npc_target_by_name,
)
from typing import (
    Any as Any, Dict as Dict, List as List,
)
import re


def _mentions(text: str, words: Any) -> bool:
    """Whether ``text`` names any of ``words`` as a whole word or phrase, with a common ending ("attacks",
    "eating"): "use" is not in "because" or "useful", nor "rent" in "current"."""
    return any(
        re.search(rf"(?<![\w']){re.escape(word)}(?:s|es|d|ed|ing)?(?![\w'])", text)
        for word in words
    )


def derive_action_candidates(simulation_state, player_input, runtime_state=None):
    candidates: list[dict[str, Any]] = []
    text = str(player_input.get("text", "") if isinstance(player_input, dict) else player_input).lower()
    target_id = _find_npc_target_by_name(simulation_state, text)

    # Deterministic inn / room rental fallback.
    # This catches flows like:
    #   "i ask bran for a room"
    #   "ill take the best one"
    # without letting "take" become pickup_item.
    inn_words = ("room", "inn", "bed", "stay", "rent", "lodging", "sleep")
    room_selection_words = ("best", "private", "cheap", "common", "standard", "normal")
    active_interactions = _safe_list((runtime_state or {}).get("active_interactions"))
    has_active_inn_interaction = any(
        _safe_str(_safe_dict(i).get("action_type")).lower() in {"rent_room", "rent_bed", "use_service"}
        or "room" in _safe_str(_safe_dict(i).get("subtype")).lower()
        or "inn" in _safe_str(_safe_dict(i).get("subtype")).lower()
        for i in active_interactions
    )
    if _mentions(text, inn_words) or (
        has_active_inn_interaction and _mentions(text, room_selection_words)
    ):
        tier = None
        if _mentions(text, ("best", "private")):
            tier = "best"
        elif _mentions(text, ("cheap", "common")):
            tier = "cheap"
        elif _mentions(text, ("standard", "normal")):
            tier = "standard"
        candidates.append(
            {
                "action_type": "rent_room",
                "target": "inn",
                "tier": tier,
                "confidence": 0.92 if tier else 0.82,
                "source": "deterministic_room_rental_fallback",
            }
        )
        return candidates

    # Passive observation: no XP path
    if _mentions(text, ["look around", "look about", "observe", "glance", "scan", "take in"]):
        candidates.append({"action_type": "observe", "priority": 4})

    # Real investigation: deliberate scrutiny
    if _mentions(text, ["investigate", "search", "examine", "inspect", "analyze"]):
        candidates.append({"action_type": "investigate", "priority": 6})

    # Unarmed combat
    if _mentions(text, ["punch", "kick", "headbutt", "slam"]):
        candidates.append({"action_type": "attack_unarmed", "priority": 10})

    # Armed / generic combat
    if _mentions(text, ["attack", "hit", "strike", "fight", "slash", "stab"]):
        candidates.append({"action_type": "attack_melee", "priority": 9})

    if _mentions(text, ["shoot", "fire", "aim"]):
        candidates.append({"action_type": "attack_ranged", "priority": 10})

    # Defense
    if _mentions(text, ["block", "defend", "shield"]):
        candidates.append({"action_type": "block", "priority": 8})
    if _mentions(text, ["dodge", "evade", "roll"]):
        candidates.append({"action_type": "dodge", "priority": 8})
    # Social
    if _mentions(text, ["persuade", "convince", "talk", "negotiate"]):
        candidates.append({"action_type": "persuade", "priority": 7, "target_id": target_id})
    if _mentions(text, ["threaten", "intimidate", "scare"]):
        candidates.append({"action_type": "intimidate", "priority": 7, "target_id": target_id})

    # Broad open-ended social / activity lane.
    # The semantic action interpreter will determine whether this is darts,
    # singing, drinking, hugging, competing, trading, ritual, etc.
    if _mentions(text, [
        "play", "challenge", "invite", "join", "dance", "sing", "perform",
        "hug", "embrace", "kiss", "toast", "drink with", "buy", "trade",
        "bet", "gamble", "pray", "ritual", "compete", "contest",
    ]):
        candidates.append({"action_type": "social_activity", "priority": 8, "target_id": target_id})
    # Stealth
    if _mentions(text, ["sneak", "hide", "stealth"]):
        candidates.append({"action_type": "sneak", "priority": 6})
    if _mentions(text, ["hack", "crack", "decrypt"]):
        candidates.append({"action_type": "hack", "priority": 6})
    if _mentions(text, ["cast", "spell", "magic"]):
        candidates.append({"action_type": "cast_spell", "priority": 7})
    if _mentions(text, ["threat", "warn", "menace"]):
        candidates.append({"action_type": "threat", "priority": 7, "target_id": target_id})
    # --- Inn / room rental intent (deterministic fallback) ---
    if _mentions(text, ["room", "inn", "bed", "stay", "rent", "lodging"]):
        tier = None
        if _mentions(text, ("best", "private")):
            tier = "best"
        elif _mentions(text, ("cheap", "common")):
            tier = "cheap"
        elif _mentions(text, ("standard", "normal")):
            tier = "standard"

        candidates.append({
            "action_type": "rent_room",
            "target": "inn",
            "tier": tier,
            "confidence": 0.9
        })

        return candidates
    # Items
    prior_contract = _safe_dict((runtime_state or {}).get("last_turn_contract"))
    prior_service = _safe_dict(prior_contract.get("service_result"))
    if not prior_service:
        prior_resolved = _safe_dict(
            prior_contract.get("resolved_result") or prior_contract.get("resolved_action")
        )
        prior_service = _safe_dict(prior_resolved.get("service_result"))
    selects_prior_offer = any(
        _safe_str(_safe_dict(offer).get("label")).strip().lower() in text
        for offer in _safe_list(prior_service.get("offers"))
        if _safe_str(_safe_dict(offer).get("label")).strip()
    )
    if (
        prior_service.get("matched")
        and selects_prior_offer
        and _mentions(text, ("i'll take", "ill take", "i will take"))
    ):
        candidates.append(
            {
                "action_type": "service_purchase",
                "priority": 11,
                "target_id": _safe_str(prior_service.get("provider_id")),
                "target_name": _safe_str(prior_service.get("provider_name")),
                "service_kind": _safe_str(prior_service.get("service_kind")),
                "confidence": 0.98,
                "source": "deterministic_prior_service_offer_selection",
            }
        )
        return candidates
    if _mentions(text, ("take", "pick up")):
        active_interactions = _safe_list((runtime_state or {}).get("active_interactions"))
        if active_interactions and _mentions(text, ("best", "private", "cheap", "common", "standard", "normal", "one")):
            return []
        candidates.append(
            {
                "action_type": "pickup_item",
                "confidence": 0.6,
                "source": "keyword_pickup",
            }
        )
    if _mentions(text, ["equip", "wear", "wield"]):
        candidates.append({"action_type": "equip_item", "priority": 5})
    if _mentions(text, ["use", "drink", "eat", "consume", "quaff"]):
        candidates.append({"action_type": "use_item", "priority": 9})

    if _mentions(text, ["flee", "retreat", "escape", "withdraw", "run away"]):
        candidates.append({"action_type": "flee", "priority": 10})

    if not candidates:
        # Open-ended fallback: use observe as the safe minimum,
        # then let the semantic layer refine this into a bounded semantic action.
        candidates.append({"action_type": "observe", "priority": 1, "target_id": target_id})

    candidates.sort(key=lambda c: c.get("priority", 0), reverse=True)
    return candidates


def load_runtime_session(session_id: str) -> dict[str, Any] | None:
    if not session_id:
        return None
    return load_canonical_session(session_id)


def save_runtime_session(session: dict[str, Any]) -> dict[str, Any]:
    compact = _runtime_compact_save_enabled(_safe_dict(session.get("runtime_state")))
    return save_canonical_session(session, compact=compact)


__all__ = ["derive_action_candidates", "load_runtime_session", "save_runtime_session"]
