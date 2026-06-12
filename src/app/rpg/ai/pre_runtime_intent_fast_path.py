from __future__ import annotations

from typing import Any, Dict, Iterable

FAST_PATH_SOURCE = "phase14_16_pre_runtime_intent_fast_path_v1"


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _target_from_text(text: str) -> tuple[str, str]:
    if "bran" in text:
        return "npc:bran", "Bran"
    if "elara" in text or "merchant" in text:
        return "npc:elara", "Elara"
    if "guard" in text:
        return "npc:guard", "guard"
    if "bandit" in text:
        return "enemy:road_bandit", "road bandit"
    if "rusty flagon" in text or "tavern" in text:
        return "loc:rusty_flagon", "Rusty Flagon"
    if "quarry" in text:
        return "loc:old_quarry", "old quarry"
    if "road" in text:
        return "loc:north_road", "north road"
    return "", ""


def classify_pre_runtime_intent_fast_path(
    *,
    player_input: str,
    candidate_action: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a deterministic first-call advisory for obvious manual commands.

    This helper intentionally does not decide outcomes. It only gives the
    deterministic runtime a bounded action family so obvious scripted/live commands
    can avoid an expensive pre-runtime LLM classifier call.
    """

    text = _s(player_input).strip().lower()
    if not text:
        return {}
    candidate_action = _d(candidate_action)
    target_id, target_name = _target_from_text(text)

    action_type = ""
    skill_id = ""
    reason = ""
    tags: list[str] = []

    if _contains_any(text, ("buy", "rent", "pay", "price", "coin", "silver", "afford", "room", "ration", "supplies")):
        action_type = "trade"
        skill_id = "barter"
        reason = "commerce_or_service_keyword"
        tags = ["commerce", "service"]
    elif _contains_any(text, ("attack", "strike", "defend", "fight", "combat", "confront", "threat", "wounded", "enemy")):
        action_type = "attack_melee" if _contains_any(text, ("attack", "strike")) else "threat"
        skill_id = "swordsmanship" if action_type == "attack_melee" else "intimidation"
        reason = "combat_or_threat_keyword"
        tags = ["combat", "threat"]
        if not target_id:
            target_id, target_name = "enemy:road_bandit", "road bandit"
    elif _contains_any(text, ("travel", "leave", "head ", "return", "follow", "route", "road", "landmark", "where am i", "where i am", "paths")):
        action_type = "exploration"
        reason = "travel_or_location_keyword"
        tags = ["travel", "location"]
    elif _contains_any(text, ("inspect", "investigate", "search", "look for", "tracks", "clue", "lead", "witness", "objective", "journal", "rumor", "rumour")):
        action_type = "investigate"
        skill_id = "investigation"
        reason = "investigation_keyword"
        tags = ["investigation"]
    elif _contains_any(text, ("ask", "tell", "say", "speak", "question", "remember", "repeat", "summarize", "explain", "warn", "trust")):
        action_type = "social_activity"
        reason = "social_or_memory_keyword"
        tags = ["social", "memory"] if _contains_any(text, ("remember", "repeat", "phrase", "secret", "code")) else ["social"]
    elif _contains_any(text, ("check", "current", "health", "gear", "stamina", "injuries", "money", "pack", "supplies")):
        action_type = "observe"
        reason = "observe_status_keyword"
        tags = ["observe", "status"]

    if not action_type:
        return {}

    advisory = {
        "action_type": action_type,
        "difficulty": _s(candidate_action.get("difficulty") or "normal"),
        "skill_id": skill_id,
        "intent_tags": tags,
        "narrative_goal": "Route an obvious player command through deterministic runtime without a pre-runtime intent LLM call.",
        "target_id": target_id or _s(candidate_action.get("target_id") or candidate_action.get("npc_id")),
        "target_name": target_name or _s(candidate_action.get("target_name")),
        "stateful": True,
        "needs_runtime_resolution": True,
        "visible_response": {},
        "reason": reason,
        "pre_runtime_intent_fast_path": True,
        "pre_runtime_intent_fast_path_reason": reason,
        "pre_runtime_intent_fast_path_source": FAST_PATH_SOURCE,
    }
    return advisory
