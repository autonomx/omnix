from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


@dataclass(frozen=True)
class DialogueRelevanceResult:
    ok: bool
    action_kind: str
    dialogue_kind: str
    reasons: Tuple[str, ...]
    severity: int = 0


_COMMERCE_TERMS = (
    "buy",
    "purchase",
    "sell",
    "pay",
    "rent",
    "room",
    "lodging",
    "ration",
    "rations",
    "supplies",
    "merchant",
    "shop",
    "trade",
)

_TRAVEL_TERMS = (
    "travel",
    "go to",
    "head to",
    "move to",
    "walk to",
    "ride to",
    "leave for",
    "road",
    "mill",
    "watchpost",
    "north watch",
    "route",
)

_COMBAT_TERMS = (
    "attack",
    "strike",
    "fight",
    "combat",
    "defeat",
    "kill",
    "wound",
    "press the attack",
    "intercept",
    "ambush",
)

_SOCIAL_INVESTIGATION_TERMS = (
    "ask",
    "question",
    "press",
    "talk",
    "tell",
    "report",
    "witness",
    "rumor",
    "traveler",
    "bandit road",
    "what happened",
    "who saw",
    "voss",
)

_COMMERCE_DIALOGUE_TERMS = (
    "coin",
    "price",
    "cost",
    "paid",
    "payment",
    "room",
    "lodging",
    "ration",
    "rations",
    "supplies",
    "trade",
    "buy",
    "sell",
)

_TRAVEL_DIALOGUE_TERMS = (
    "road",
    "path",
    "route",
    "arrive",
    "travel",
    "mill",
    "watchpost",
    "north",
    "tracks",
    "distance",
)

_COMBAT_DIALOGUE_TERMS = (
    "fight",
    "attack",
    "wound",
    "blood",
    "weapon",
    "enemy",
    "defeat",
    "retaliation",
    "combat",
    "injury",
)

_STALE_WITNESS_DIALOGUE_TERMS = (
    "traveler",
    "witness",
    "bandit road",
    "people saw more",
    "ask plainly",
    "old fear",
    "frightened them",
)

_STALE_TAVERN_AMBIENT_TERMS = (
    "room has been busier",
    "busier than usual",
    "tonight",
    "regulars",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _lower(value: Any) -> str:
    return _safe_str(value).lower()


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def classify_player_action(player_action: str, row: Mapping[str, Any] | None = None) -> str:
    text = _lower(player_action)
    row = _safe_dict(row)

    if _safe_list(row.get("combat_lifecycle_events")) or _contains_any(text, _COMBAT_TERMS):
        return "combat"

    if _safe_list(row.get("economy_pressure_events")) or _contains_any(text, _COMMERCE_TERMS):
        return "commerce"

    if _contains_any(text, _TRAVEL_TERMS):
        return "travel"

    if _contains_any(text, _SOCIAL_INVESTIGATION_TERMS):
        return "social_investigation"

    if text.strip() in {"wait", "listen", "observe", "look around", "watch"}:
        return "ambient_observe"

    return "general"


def classify_dialogue_text(narration: str = "", npc_line: str = "") -> str:
    text = _lower(f"{narration}\n{npc_line}")

    if _contains_any(text, _COMBAT_DIALOGUE_TERMS):
        return "combat"

    if _contains_any(text, _COMMERCE_DIALOGUE_TERMS):
        return "commerce"

    if _contains_any(text, _TRAVEL_DIALOGUE_TERMS):
        return "travel"

    if _contains_any(text, _STALE_WITNESS_DIALOGUE_TERMS):
        return "social_investigation"

    if _contains_any(text, _SOCIAL_INVESTIGATION_TERMS):
        return "social_investigation"

    if _contains_any(text, _STALE_TAVERN_AMBIENT_TERMS):
        return "ambient_tavern"

    if not text.strip():
        return "none"

    return "general"


def _speaker_from_row(row: Mapping[str, Any]) -> str:
    npc = _safe_dict(row.get("npc"))
    return _safe_str(npc.get("speaker") or row.get("npc_speaker") or row.get("speaker"))


def _npc_line_from_row(row: Mapping[str, Any]) -> str:
    npc = _safe_dict(row.get("npc"))
    return _safe_str(npc.get("line") or row.get("npc_line") or row.get("dialogue"))


def _narration_from_row(row: Mapping[str, Any]) -> str:
    return _safe_str(row.get("narration") or row.get("selected_narration") or row.get("display_narration"))


def _current_location(row: Mapping[str, Any]) -> str:
    for key in ("location_id", "current_location_id", "scene_id"):
        value = _safe_str(row.get(key))
        if value:
            return value

    state = _safe_dict(row.get("state"))
    for key in ("location_id", "current_location_id", "scene_id"):
        value = _safe_str(state.get(key))
        if value:
            return value

    return ""


def _speaker_presence(row: Mapping[str, Any], speaker: str) -> Dict[str, Any]:
    presence = _safe_dict(row.get("npc_presence"))
    speaker_l = speaker.lower()

    for npc_id, raw in presence.items():
        p = _safe_dict(raw)
        if speaker_l and (
            speaker_l in _safe_str(npc_id).lower()
            or speaker_l in _safe_str(p.get("npc_id")).lower()
            or speaker_l in _safe_str(p.get("name")).lower()
        ):
            return p

    return {}


def validate_dialogue_action_relevance(
    *,
    player_action: str,
    row: Mapping[str, Any],
    display_source: str = "",
    narration: str = "",
    npc_speaker: str = "",
    npc_line: str = "",
) -> Dict[str, Any]:
    row = _safe_dict(row)
    narration = narration if narration else _narration_from_row(row)
    npc_line = npc_line if npc_line else _npc_line_from_row(row)
    npc_speaker = npc_speaker if npc_speaker else _speaker_from_row(row)
    display_source = _safe_str(display_source or row.get("dialogue_source") or row.get("display_source"))

    action_kind = classify_player_action(player_action, row)
    dialogue_kind = classify_dialogue_text(narration, npc_line)

    reasons: List[str] = []
    severity = 0

    if action_kind == "commerce" and dialogue_kind in {"social_investigation", "ambient_tavern", "travel", "combat"}:
        reasons.append("commerce_action_dialogue_mismatch")
        severity = max(severity, 3)

    if action_kind == "travel" and dialogue_kind in {"social_investigation", "ambient_tavern", "commerce"}:
        reasons.append("travel_action_dialogue_mismatch")
        severity = max(severity, 3)

    if action_kind == "combat" and dialogue_kind in {"social_investigation", "ambient_tavern", "commerce", "travel"}:
        reasons.append("combat_action_dialogue_mismatch")
        severity = max(severity, 3)

    if action_kind == "commerce" and "hook:" in display_source:
        reasons.append("commerce_action_hook_display_blocked")
        severity = max(severity, 3)

    if action_kind == "travel" and "conversation_beat" in display_source:
        reasons.append("travel_action_conversation_beat_blocked")
        severity = max(severity, 2)

    if action_kind == "combat" and "conversation_beat" in display_source:
        reasons.append("combat_action_conversation_beat_blocked")
        severity = max(severity, 3)

    text = _lower(f"{narration}\n{npc_line}")
    if action_kind not in {"social_investigation", "ambient_observe"} and _contains_any(text, _STALE_WITNESS_DIALOGUE_TERMS):
        reasons.append("stale_witness_dialogue_for_unrelated_action")
        severity = max(severity, 3)

    if action_kind not in {"ambient_observe", "social_investigation", "commerce"} and _contains_any(text, _STALE_TAVERN_AMBIENT_TERMS):
        reasons.append("stale_tavern_ambient_dialogue_for_unrelated_action")
        severity = max(severity, 2)

    if npc_speaker:
        current_location = _current_location(row)
        presence = _speaker_presence(row, npc_speaker)
        speaker_location = _safe_str(presence.get("location_id"))
        availability = _safe_str(presence.get("availability"))

        if current_location and speaker_location and speaker_location != current_location:
            reasons.append("speaker_presence_mismatch")
            severity = max(severity, 3)

        if availability == "unavailable":
            reasons.append("speaker_unavailable")
            severity = max(severity, 2)

    ok = not reasons

    return {
        "ok": ok,
        "action_kind": action_kind,
        "dialogue_kind": dialogue_kind,
        "display_source": display_source,
        "npc_speaker": npc_speaker,
        "reasons": reasons,
        "severity": severity,
        "player_action": _safe_str(player_action),
        "narration_preview": _safe_str(narration)[:240],
        "npc_line_preview": _safe_str(npc_line)[:240],
    }


def should_allow_display_source(
    *,
    player_action: str,
    display_source: str,
    row: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    row = _safe_dict(row)
    action_kind = classify_player_action(player_action, row)
    source = _lower(display_source)

    blocked_reasons: List[str] = []

    if action_kind in {"commerce", "combat", "travel"} and "story_hook_display" in source:
        blocked_reasons.append(f"{action_kind}_blocks_story_hook_display")

    if action_kind in {"combat", "travel"} and "conversation_beat" in source:
        blocked_reasons.append(f"{action_kind}_blocks_conversation_beat")

    if action_kind == "commerce" and ("witness" in source or "hook:" in source):
        blocked_reasons.append("commerce_blocks_witness_hook_display")

    return {
        "ok": not blocked_reasons,
        "action_kind": action_kind,
        "display_source": display_source,
        "blocked_reasons": blocked_reasons,
    }


def build_action_relevant_fallback(
    *,
    player_action: str,
    row: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    row = _safe_dict(row)
    action_kind = classify_player_action(player_action, row)

    if action_kind == "commerce":
        narration = "The exchange is handled as a practical transaction, with coin and goods kept to the authoritative result."
        action = "The commerce action resolves according to the turn contract."
    elif action_kind == "travel":
        narration = "The movement resolves through the current route and location state without adding unrelated conversation."
        action = "The travel action resolves according to the turn contract."
    elif action_kind == "combat":
        narration = "The combat moment resolves from the deterministic combat state and recorded consequences."
        action = "The combat action resolves according to the turn contract."
    elif action_kind == "social_investigation":
        narration = "The question is handled against the current social and story state."
        action = "The social action resolves according to the turn contract."
    else:
        narration = "The moment resolves without adding unrelated dialogue."
        action = "The action resolves according to the turn contract."

    return {
        "format_version": "rpg_narration_v2",
        "narration": narration,
        "action": action,
        "npc": {},
        "reward": {},
        "followup_hooks": [],
        "dialogue_source": "deterministic_action_relevance_fallback",
        "action_kind": action_kind,
    }