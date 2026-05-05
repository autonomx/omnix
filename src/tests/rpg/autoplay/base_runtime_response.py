from __future__ import annotations

import json
import re
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())


def is_echo_narration(*, player_action: str, narration: str) -> bool:
    action = _norm(player_action)
    text = _norm(narration)
    return bool(action and text and (action == text or text == action.rstrip(".") or text == action + "."))


def classify_autoplay_action(player_action: str) -> str:
    text = _norm(player_action)
    if any(word in text for word in ["ask", "talk", "tell", "speak", "question", "report", "explain", "share", "approach"]):
        return "social"
    if any(word in text for word in ["look", "inspect", "search", "observe", "scan", "examine", "listen"]):
        return "exploration"
    if any(word in text for word in ["walk", "travel", "leave", "follow", "pursue", "road", "outside"]):
        return "travel"
    if any(word in text for word in ["buy", "rent", "room", "drink", "meal", "service"]):
        return "service"
    return "general"


def infer_target_npc(player_action: str, simulation_state: Dict[str, Any]) -> str:
    text = _norm(player_action)
    known_names = ["bran", "mira", "cloaked traveler", "traveler", "patron", "innkeeper"]
    for name in known_names:
        if name in text:
            if name == "innkeeper":
                return "Bran"
            if name == "traveler":
                return "Cloaked Traveler"
            if name == "patron":
                return "Local Patron"
            return " ".join(part.capitalize() for part in name.split())

    profiles = _safe_dict(_safe_dict(simulation_state.get("npc_profile_state")).get("profiles"))
    for profile in profiles.values():
        profile = _safe_dict(profile)
        name = _safe_str(profile.get("name"))
        if name and _norm(name) in text:
            return name
    return ""


def _npc_line_for_action(*, npc_name: str, player_action: str, simulation_state: Dict[str, Any]) -> str:
    text = _norm(player_action)
    npc = npc_name or "Someone nearby"

    if npc == "Bran":
        if "bandit" in text or "road" in text:
            return "If the bandit road is involved, keep your eyes open. Trouble out there rarely travels alone."
        if "witness" in text or "traveler" in text or "found" in text:
            return "Tell me exactly what you found. Around here, one small detail can turn a rumor into a trail."
        if "room" in text or "rent" in text:
            return "A room can be arranged, but not before I know whether tonight's trouble is about to land on my doorstep."
        return "I can talk, but make it useful. The tavern is busy, and everyone is listening for trouble."

    if npc == "Mira":
        if "witness" in text or "traveler" in text or "cloak" in text:
            return "I remember the cloak. Whoever wore it moved like they wanted the room to forget them."
        return "I notice more than people think. Ask clearly, and I will tell you what I saw."

    if npc == "Cloaked Traveler":
        if "bandit" in text or "road" in text:
            return "The road is not safe. I kept walking because stopping would have made me easier to find."
        return "I did not want to be part of this, but I saw enough to know the danger was real."

    if npc == "Local Patron":
        if "witness" in text or "traveler" in text:
            return "There was a traveler, yes. Hood up, shoulders tight, left quicker than most folk finish their drink."
        if "bandit" in text:
            return "Bandits? People whisper about the road, but whispering is safer than naming names."
        return "I might know something, but strangers asking questions make people cautious."

    return "The answer comes cautiously, shaped more by local fear than certainty."


def build_deterministic_base_response(
    *,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_index: int,
) -> Dict[str, Any]:
    """Presentation-only fallback response for autoplay report quality.

    This does not mutate simulation state and does not decide story outcomes.
    It exists so non-hook turns have a visible RPG response instead of echoed
    player input.
    """
    action_type = classify_autoplay_action(player_action)
    npc_name = infer_target_npc(player_action, simulation_state)
    text = _norm(player_action)

    if action_type == "social":
        speaker = npc_name or "Local Patron"
        line = _npc_line_for_action(
            npc_name=speaker,
            player_action=player_action,
            simulation_state=simulation_state,
        )
        narration = f"{speaker} weighs the question before answering, and the tavern noise seems to pull back around the exchange."
    elif action_type == "exploration":
        speaker = ""
        line = ""
        if "listen" in text or "rumor" in text:
            speaker = "Nearby Voices"
            line = "The room's rumors circle the same concerns: a hurried traveler, an unsafe road, and Bran watching the door too often."
        narration = "The search turns up small but grounded details: scuffed floorboards, watchful patrons, and signs that the tavern has been tense for more than one night."
    elif action_type == "travel":
        speaker = ""
        line = ""
        narration = "The movement shifts the scene's pressure outward, away from the tavern's warm light and toward the uncertainty of the road."
    elif action_type == "service":
        speaker = npc_name or "Bran"
        line = "I can handle ordinary business, but tonight is not ordinary. Trouble has a way of changing prices and priorities."
        narration = "The practical request lands against the tavern's unease, turning routine business into part of the night's tension."
    else:
        speaker = ""
        line = ""
        narration = "The action changes the moment slightly, but no major consequence follows from it yet."

    payload = {
        "format_version": "autoplay_base_response_v1",
        "source": "deterministic_base_runtime_response",
        "turn_index": int(turn_index),
        "action_type": action_type,
        "narration": narration,
        "npc": {
            "speaker": speaker,
            "line": line,
        },
        "authoritative_changes": False,
        "notes": [
            "presentation_only",
            "does_not_award_rewards",
            "does_not_complete_objectives",
            "does_not_mutate_simulation_state",
        ],
    }
    return payload


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _call_provider_text(provider: Any, prompt: str, *, max_tokens: int = 220) -> str:
    if provider is None:
        return ""
    for method_name in ("chat", "complete", "generate", "invoke"):
        method = getattr(provider, method_name, None)
        if not callable(method):
            continue
        try:
            if method_name == "chat":
                response = method(
                    [
                        {
                            "role": "system",
                            "content": "You are an RPG presentation layer. Return JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                )
            else:
                response = method(prompt, max_tokens=max_tokens)
            if isinstance(response, str):
                return response
            if isinstance(response, dict):
                return _safe_str(response.get("content") or response.get("text") or response.get("response"))
            content = getattr(response, "content", "")
            if content:
                return str(content)
        except Exception:
            continue
    return ""


def build_provider_base_response(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_index: int,
    max_tokens: int = 220,
) -> Dict[str, Any]:
    action_type = classify_autoplay_action(player_action)
    npc_name = infer_target_npc(player_action, simulation_state)
    prompt = {
        "task": "Write a presentation-only RPG response for this turn.",
        "rules": [
            "Return JSON only.",
            "Do not decide rewards, XP, objective completion, item gain, damage, or quest outcomes.",
            "Do not repeat the player action as narration.",
            "If the action addresses an NPC, include npc.speaker and npc.line.",
            "Keep narration 1-3 sentences.",
        ],
        "schema": {
            "format_version": "autoplay_base_response_v1",
            "narration": "scene response, not player-action echo",
            "npc": {"speaker": "NPC name or empty", "line": "NPC line or empty"},
        },
        "player_action": player_action,
        "action_type": action_type,
        "target_npc": npc_name,
    }
    raw = _call_provider_text(provider, json.dumps(prompt, ensure_ascii=False), max_tokens=max_tokens)
    parsed = _extract_json_object(raw)
    narration = _safe_str(parsed.get("narration"))
    npc = _safe_dict(parsed.get("npc"))
    if not narration or is_echo_narration(player_action=player_action, narration=narration):
        return {}
    return {
        "format_version": "autoplay_base_response_v1",
        "source": "provider_base_runtime_response",
        "turn_index": int(turn_index),
        "action_type": action_type,
        "narration": narration,
        "npc": {
            "speaker": _safe_str(npc.get("speaker")),
            "line": _safe_str(npc.get("line")),
        },
        "raw_provider_response": raw,
        "authoritative_changes": False,
        "notes": [
            "presentation_only",
            "does_not_award_rewards",
            "does_not_complete_objectives",
            "does_not_mutate_simulation_state",
        ],
    }


def build_autoplay_base_response(
    *,
    provider: Any = None,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_index: int,
    use_provider: bool = False,
    max_tokens: int = 220,
) -> Dict[str, Any]:
    if use_provider:
        provider_payload = build_provider_base_response(
            provider=provider,
            player_action=player_action,
            simulation_state=simulation_state,
            turn_index=turn_index,
            max_tokens=max_tokens,
        )
        if provider_payload:
            return provider_payload
    return build_deterministic_base_response(
        player_action=player_action,
        simulation_state=simulation_state,
        turn_index=turn_index,
    )