"""Deterministic fallback narration helpers."""
from __future__ import annotations

import logging

from typing import Any, Dict, List, cast

from app.apps.rpg.narration.dialogue_state import update_dialogue_state
from app.apps.rpg.narration.npc_dialogue.intelligence import (
    build_npc_intelligence_prompt,
    normalize_npc_intelligence_payload,
    npc_line_is_invalid,
)
from app.apps.rpg.foundation.provider_access import get_provider  # RPG's route, its calls counted
from app.apps.rpg.foundation.state.people import world_people

from .runtime_narration_common import NARRATION_FORMAT_VERSION, _norm, _safe_str
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list

logger = logging.getLogger(__name__)

def _recent_npc_lines(simulation_state: Dict[str, Any], speaker: str, *, limit: int = 8) -> List[str]:
    simulation_state = _safe_dict(simulation_state)
    rows: List[Dict[str, Any]] = []
    for key in ("recent_turns", "turn_history", "transcript", "narration_history"):
        rows.extend([row for row in _safe_list(simulation_state.get(key)) if isinstance(row, dict)])
    lines: List[str] = []
    for row in rows[-max(1, int(limit or 8)):]:
        npc = _safe_dict(row.get("npc"))
        row_speaker = _safe_str(npc.get("speaker") or row.get("speaker"))
        line = _safe_str(npc.get("line") or row.get("npc_line") or row.get("line"))
        if speaker and row_speaker.lower() == speaker.lower() and line:
            lines.append(line)
    return lines[-limit:]


def _build_dialogue_state_update_payload(
    *,
    simulation_state: Dict[str, Any],
    speaker: str,
    player_action: str,
    npc_line: str,
) -> Dict[str, Any]:
    if not speaker or not npc_line:
        return {}
    state = _safe_dict(simulation_state)
    try:
        update_dialogue_state(
            state,
            npc_id=speaker,
            player_action=player_action,
            npc_line=npc_line,
            facts_revealed=_known_facts_for_npc_reply(state, player_action),
        )
        return _safe_dict(state.get("dialogue_state"))
    except Exception:
        return {}


def _known_facts_for_npc_reply(
    simulation_state: Dict[str, Any],
    player_action: str = "",
) -> List[str]:
    facts = []
    for key in ("world_events", "recent_world_events", "quest_events", "journal_entries"):
        for row in _safe_list(_safe_dict(simulation_state).get(key)):
            if isinstance(row, dict):
                text = _safe_str(row.get("summary") or row.get("text") or row.get("description"))
            else:
                text = _safe_str(row)
            if text:
                facts.append(text)
    quest_state = _safe_dict(_safe_dict(simulation_state).get("quest_progress"))
    for quest in _safe_dict(quest_state.get("quests")).values():
        quest = _safe_dict(quest)
        title = _safe_str(quest.get("title"))
        if title:
            facts.append(f"Quest: {title}")
        for obj in _safe_list(quest.get("objectives")):
            obj = _safe_dict(obj)
            if not obj.get("completed"):
                facts.append(_safe_str(obj.get("summary") or obj.get("objective_text")))
    player_prompt = _safe_str(player_action).strip()
    if player_prompt:
        facts.append(f"Player asked: {player_prompt}")
    return [fact for fact in facts if fact][:12]


def is_echo_narration(*, player_action: str, narration: str) -> bool:
    action = _norm(player_action)
    text = _norm(narration)
    return bool(action and text and (text == action or text == action.rstrip(".") or text == action + "."))


def classify_player_action(player_action: str) -> str:
    text = _norm(player_action)
    if any(word in text for word in ["ask", "talk", "tell", "speak", "question", "report", "explain", "share", "approach", "convince", "persuade"]):
        return "social"
    if any(word in text for word in ["look", "inspect", "search", "observe", "scan", "examine", "listen"]):
        return "exploration"
    if any(word in text for word in ["walk", "travel", "leave", "follow", "pursue", "road", "outside"]):
        return "travel"
    if any(word in text for word in ["attack", "strike", "hit", "shoot", "cast", "defend"]):
        return "combat"
    if any(word in text for word in ["buy", "sell", "rent", "room", "drink", "meal", "service"]):
        return "service"
    return "general"


def infer_npc_speaker(player_action: str, simulation_state: Dict[str, Any] | None = None) -> str:
    """The person the player addresses by name: one of the world's people (the engine names nobody of its own)."""
    text = _norm(player_action)
    simulation_state = _safe_dict(simulation_state)
    rows = [
        *world_people(simulation_state).values(),
        *_safe_dict(_safe_dict(simulation_state.get("npc_profile_state")).get("profiles")).values(),
    ]
    for row in rows:
        name = _safe_str(_safe_dict(row).get("name"))
        if name and _norm(name) in text:
            return name
    return ""


def _fallback_npc_line(*, speaker: str) -> str:
    """A reply that claims nothing: the fallback is presentation only and knows no one's story."""
    if not speaker:
        return ""
    return "The reply comes cautiously, shaped by the pressure in the room."


def build_deterministic_narration_payload(
    *,
    player_action: str,
    simulation_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a safe presentation-only narration payload.

    This is a fallback, not a simulation authority. It describes only that the
    moment responds to the player's action. It does not award, complete, mutate,
    or invent authoritative facts.
    """
    simulation_state = _safe_dict(simulation_state)
    turn_contract = _safe_dict(turn_contract)
    action_type = classify_player_action(player_action)
    speaker = infer_npc_speaker(player_action, simulation_state)
    npc_line = ""
    npc_intel: Dict[str, Any] = {}

    if action_type == "social":
        speaker = speaker or "Local Patron"
        narration = f"{speaker} reacts to the question, and the surrounding noise seems to thin as the conversation draws attention."
        recent_lines = _recent_npc_lines(simulation_state, speaker)
        try:
            npc_messages = build_npc_intelligence_prompt(
                speaker=speaker,
                player_action=player_action,
                npc_profile=_safe_dict(_safe_dict(simulation_state).get("npc_profiles")).get(speaker, {}),
                social_state=_safe_dict(_safe_dict(simulation_state).get("social_state")).get(speaker, {}),
                known_facts=_known_facts_for_npc_reply(simulation_state),
                recent_lines=recent_lines,
                active_objectives=_safe_list(_safe_dict(simulation_state).get("active_objectives")),
            )
            raw = cast(Any, get_provider()).chat(messages=npc_messages, temperature=0.35, max_tokens=260)
            npc_intel = normalize_npc_intelligence_payload(raw)
            if not npc_line_is_invalid(npc_intel.get("line", ""), recent_lines):
                npc_line = npc_intel["line"]
        except Exception:
            logger.debug("suppressed error in %s", "build_deterministic_narration_payload", exc_info=True)

        if not npc_line:
            npc_line = _fallback_npc_line(speaker=speaker)
    elif action_type == "exploration":
        narration = "The search draws out grounded details from the scene: small marks, watchful faces, and signs of recent tension."
        npc_line = ""
    elif action_type == "travel":
        narration = "The scene shifts with the movement, carrying the pressure of the current lead into the space ahead."
        npc_line = ""
    elif action_type == "combat":
        narration = "The hostile motion sharpens the moment, but the actual outcome remains bound to the combat result."
        npc_line = ""
    elif action_type == "service" and speaker:
        narration = "The practical request lands against the unease of the room, making ordinary business feel less ordinary."
        recent_lines = _recent_npc_lines(simulation_state, speaker)
        try:
            npc_messages = build_npc_intelligence_prompt(
                speaker=speaker,
                player_action=player_action,
                npc_profile=_safe_dict(_safe_dict(simulation_state).get("npc_profiles")).get(speaker, {}),
                social_state=_safe_dict(_safe_dict(simulation_state).get("social_state")).get(speaker, {}),
                known_facts=_known_facts_for_npc_reply(simulation_state),
                recent_lines=recent_lines,
                active_objectives=_safe_list(_safe_dict(simulation_state).get("active_objectives")),
            )
            raw = cast(Any, get_provider()).chat(messages=npc_messages, temperature=0.35, max_tokens=260)
            npc_intel = normalize_npc_intelligence_payload(raw)
            if not npc_line_is_invalid(npc_intel.get("line", ""), recent_lines):
                npc_line = npc_intel["line"]
        except Exception:
            logger.debug("suppressed error in %s", "build_deterministic_narration_payload", exc_info=True)

        if not npc_line:
            npc_line = _fallback_npc_line(speaker=speaker)
    else:
        narration = "The moment responds without producing a major new consequence."
        npc_line = ""

    if is_echo_narration(player_action=player_action, narration=narration):
        narration = "The scene responds with a grounded beat rather than merely repeating the attempted action."

    if speaker and npc_line:
        try:
            update_dialogue_state(
                simulation_state,
                npc_id=speaker,
                player_action=player_action,
                npc_line=npc_line,
                facts_revealed=_known_facts_for_npc_reply(simulation_state, player_action),
            )
            # Also update recent_turns for global recent line tracking
            recent_turns = simulation_state.setdefault("recent_turns", [])
            recent_turns.append({
                "npc": {
                    "speaker": speaker,
                    "line": npc_line,
                }
            })
            simulation_state["recent_turns"] = recent_turns[-8:]
        except Exception:
            logger.debug("suppressed error in %s", "build_deterministic_narration_payload", exc_info=True)

    dialogue_state_update = _build_dialogue_state_update_payload(
        simulation_state=simulation_state,
        speaker=speaker,
        player_action=player_action,
        npc_line=npc_line,
    )

    return {
        "format_version": NARRATION_FORMAT_VERSION,
        "narration": narration,
        "action": _safe_str(turn_contract.get("summary") or turn_contract.get("action") or "The action is acknowledged by the scene."),
        "npc": {
            "speaker": speaker if npc_line else "",
            "line": npc_line,
        },
        "reward": "",
        "followup_hooks": [],
        "dialogue_state_update": dialogue_state_update,
        "source": "deterministic_runtime_narration_fallback",
        "authoritative_changes": False,
    }
