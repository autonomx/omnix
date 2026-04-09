from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_background_chatter_lines(location_id: str, recent_events: List[Dict[str, Any]]) -> List[str]:
    """Generate background crowd chatter lines for a location.

    These are short, atmospheric one-liners based on recent events nearby.
    They are not attributed to specific NPCs — they represent the ambient
    sound of townsfolk, merchants, travelers, etc.
    """
    location_id = _safe_str(location_id)
    lines: List[str] = []

    if not recent_events:
        return lines

    for event in recent_events[-4:]:
        event = _safe_dict(event)
        event_type = _safe_str(event.get("type")).lower()
        summary = _safe_str(event.get("summary") or event.get("description"))

        if event_type in {"attack", "combat", "retaliate"}:
            lines.append("Someone mutters about the recent fighting.")
            lines.append("A trader asks nervously if the roads are safe.")
        elif event_type in {"theft", "sabotage", "steal"}:
            lines.append("A merchant complains about missing goods.")
            lines.append("Whispers about a thief circulate through the crowd.")
        elif event_type in {"arrival", "migration"}:
            lines.append("Newcomers are spotted entering the area.")
        elif event_type in {"trade", "negotiate", "commerce"}:
            lines.append("Merchants haggle over prices in raised voices.")
        elif event_type in {"festival", "celebration", "ceremony"}:
            lines.append("The crowd buzzes with excitement about the festivities.")
        elif event_type in {"incident", "destabilize", "threaten"}:
            lines.append("The crowd murmurs about what just happened.")
            lines.append("People exchange worried glances.")
        elif summary:
            lines.append(f"Voices in the crowd: \"{summary[:80]}\"")
        else:
            lines.append("The crowd murmurs about recent happenings.")

    # Dedupe and bound
    seen = set()
    unique: List[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return unique[:6]
