"""Bounded provider-backed intent fast paths for interactive matrix runs.

Phase 13.4 uses accepted interactive-matrix performance evidence to avoid the
first-call advisory provider round trip for a small set of known-safe matrix
intent categories.  The helper is opt-in through fast-turn performance overrides
and remains advisory-only: canonical runtime still resolves state.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

FAST_PATH_SOURCE = "phase13_4_provider_backed_intent_fast_path_v1"
_FAST_TARGETS = {
    "commerce_food_purchase",
    "quest_no_backed_state",
    "rumor_news_no_backed_state",
    "party_companion_recruitment",
    "npc_dialogue_persona",
}


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    return "" if value is None else str(value)


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


def provider_backed_fast_path_enabled(performance_override: Dict[str, Any] | None) -> bool:
    override = _d(performance_override)
    return _b(override.get("fast_turn_mode"), False) and _b(
        override.get("enable_provider_backed_intent_fast_path"), True
    )


def _classify_text(text: str) -> Dict[str, Any]:
    if any(term in text for term in ("rumor", "rumors", "rumour", "rumours", "news")):
        service_kind = "news" if "news" in text and "rumor" not in text else "rumor"
        return {"category": "rumor_news_no_backed_state", "action_type": "rumor_inquiry", "target_id": "npc:Bran", "target_name": "Bran", "service_kind": service_kind}
    if any(term in text for term in ("quest", "quests", "work", "job", "jobs", "task", "errand")):
        service_kind = "work" if any(term in text for term in ("work", "job", "jobs", "task", "errand")) else "quest"
        action_type = "work_inquiry" if service_kind == "work" else "quest_inquiry"
        return {"category": "quest_no_backed_state", "action_type": action_type, "target_id": "npc:Bran", "target_name": "Bran", "service_kind": service_kind}
    if any(term in text for term in ("join my party", "join party", "companion", "stay close", "close as my companion")):
        return {"category": "party_companion_recruitment", "action_type": "talk", "target_id": "npc:Bran", "target_name": "Bran", "service_kind": "unknown"}
    if any(term in text for term in ("food", "stew", "bread", "meal", "ration", "rations", "provision", "provisions", "price", "how much", "buy", "for sale")):
        action_type = "service_purchase" if any(term in text for term in ("buy", "purchase", "i'll take", "ill take", "i will take")) else "service_inquiry"
        return {"category": "commerce_food_purchase", "action_type": action_type, "target_id": "npc:Bran", "target_name": "Bran", "service_kind": "meal"}
    if "bran" in text and any(term in text for term in ("who are you", "what do you know", "this place", "tell me")):
        return {"category": "npc_dialogue_persona", "action_type": "talk", "target_id": "npc:Bran", "target_name": "Bran", "service_kind": "unknown"}
    return {}


def build_provider_backed_fast_path_advisory(
    *,
    player_input: str,
    performance_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not provider_backed_fast_path_enabled(performance_override):
        return {}
    text = _s(player_input).strip().lower()
    classification = _classify_text(text)
    if not classification or classification.get("category") not in _FAST_TARGETS:
        return {}
    action = {
        "action_type": classification["action_type"],
        "target_id": classification["target_id"],
        "target_name": classification["target_name"],
        "service_kind": classification["service_kind"],
        "metadata": {
            "first_call_advisory": True,
            "provider_backed_intent_fast_path": True,
            "fast_path_category": classification["category"],
            "source": FAST_PATH_SOURCE,
        },
    }
    diagnostics = {
        "source": FAST_PATH_SOURCE,
        "provider_parse_ok": True,
        "raw_text": "",
        "prompt_preview": "phase13_4 deterministic provider-backed intent fast path",
        "turn_grounding_packet": {
            "format_version": "phase13_4_provider_backed_intent_packet_v1",
            "player_input": _s(player_input),
            "fast_path_category": classification["category"],
            "priority_context": {"addressed_npc_ids": [classification["target_id"]]},
            "fast_path_action": deepcopy(action),
        },
    }
    return {
        "action_type": classification["action_type"],
        "target_id": classification["target_id"],
        "target_name": classification["target_name"],
        "stateful": True,
        "needs_runtime_resolution": True,
        "service_kind": classification["service_kind"],
        "provider_backed_intent_fast_path": True,
        "fast_path_category": classification["category"],
        "source": FAST_PATH_SOURCE,
        "first_call_grounding_diagnostics": diagnostics,
    }
