from __future__ import annotations

from typing import Any, Dict


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def conversation_can_generate_rumor(conversation: Dict[str, Any]) -> bool:
    topic = _safe_dict(_safe_dict(conversation).get("topic"))
    return _safe_str(topic.get("type")) in {"moral_conflict", "plan_reaction", "event_commentary", "faction_tension"}


def build_rumor_from_conversation(conversation: Dict[str, Any]) -> Dict[str, Any]:
    conversation = _safe_dict(conversation)
    topic = _safe_dict(conversation.get("topic"))
    return {
        "type": "rumor",
        "anchor": _safe_str(topic.get("anchor")),
        "summary": _safe_str(topic.get("summary")) or "People are talking.",
    }
