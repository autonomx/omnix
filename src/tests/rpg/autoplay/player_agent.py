from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from tests.rpg.autoplay.strategy_profiles import build_strategy_guidance

PLAYER_AGENT_FORMAT_VERSION = "rpg_player_action_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def build_player_agent_prompt(
    *,
    player_action_context: Dict[str, Any],
    recent_transcript: List[Dict[str, Any]] | None = None,
    strategy: str = "balanced_story_player",
    progress_quality_metrics: Dict[str, Any] | None = None,
    diversity_metrics: Dict[str, Any] | None = None,
) -> str:
    """Build the player-agent prompt.

    The prompt intentionally receives player-visible action context, not raw
    simulation state. The LLM is only choosing the next action.
    """
    recent_transcript = recent_transcript or []
    compact_recent = [
        {
            "turn_index": row.get("turn_index"),
            "player_action": row.get("player_action"),
            "narration": row.get("narration"),
            "selected_action_reason": row.get("selected_action_reason"),
        }
        for row in recent_transcript[-8:]
        if isinstance(row, dict)
    ]

    payload = {
        "strategy": strategy,
        "strategy_guidance": build_strategy_guidance(
            strategy=strategy,
            progress_quality_metrics=progress_quality_metrics,
            diversity_metrics=diversity_metrics,
            recent_transcript=recent_transcript,
        ),
        "player_action_context": player_action_context,
        "recent_transcript": compact_recent,
    }
    return (
        "You are playing an RPG as the player character.\n"
        "Choose exactly one next player action.\n\n"
        "Rules:\n"
        "- Use only player-visible context.\n"
        "- Do not narrate the outcome.\n"
        "- Do not decide success or failure.\n"
        "- Do not invent rewards, XP, gold, loot, deaths, quest completion, or hidden facts.\n"
        "- Prefer actions that pursue active objectives, interact with nearby NPCs, or investigate grounded story leads.\n"
        "- Avoid repeating the same action unless there is a clear reason.\n"
        "- If the strategy guidance says anti-stall is active, choose a meaningfully different approach from recent actions.\n"
        "- If objective-focused turns are not advancing, try a different grounded route: inspect, ask someone else, travel, review clues, or change the question.\n"
        "- Return JSON only.\n\n"
        "Required JSON format:\n"
        "{\n"
        '  "format_version": "rpg_player_action_v1",\n'
        '  "intent": "short intent",\n'
        '  "action": "single player-facing action command",\n'
        '  "reason": "why this action was chosen",\n'
        '  "risk": "low|medium|high",\n'
        '  "goal_id": "optional objective_id"\n'
        "}\n\n"
        "Context:\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    )


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise ValueError("empty_player_agent_response")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("player_agent_response_missing_json_object")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("player_agent_response_json_not_object")
    return parsed


def parse_player_agent_response(text: str) -> Dict[str, Any]:
    parsed = _extract_json_object(text)
    action = _safe_str(parsed.get("action")).strip()
    if not action:
        return {
            "ok": False,
            "reason": "missing_action",
            "raw": text,
            "parsed": parsed,
        }

    risk = _safe_str(parsed.get("risk")).lower() or "medium"
    if risk not in {"low", "medium", "high"}:
        risk = "medium"

    return {
        "ok": True,
        "format_version": PLAYER_AGENT_FORMAT_VERSION,
        "intent": _safe_str(parsed.get("intent"))[:240],
        "action": action[:1000],
        "reason": _safe_str(parsed.get("reason"))[:1000],
        "risk": risk,
        "goal_id": _safe_str(parsed.get("goal_id"))[:240],
        "raw": text,
        "parsed": parsed,
    }


def choose_fallback_player_action(
    *,
    player_action_context: Dict[str, Any],
    recent_transcript: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Deterministic fallback when the player-agent LLM fails.

    Prefer the first suggested action. If there are no suggestions, observe.
    """
    recent_transcript = recent_transcript or []
    suggestions = [
        _safe_dict(row)
        for row in _safe_list(_safe_dict(player_action_context).get("suggested_actions"))
        if isinstance(row, dict)
    ]
    recent_actions = [
        _safe_str(row.get("player_action")).strip().lower()
        for row in recent_transcript[-8:]
        if _safe_str(row.get("player_action")).strip()
    ]
    recent_counts = {
        action: recent_actions.count(action)
        for action in set(recent_actions)
    }

    if suggestions:
        # Prefer a high-priority suggestion that has not just repeated several
        # times. This keeps fallback useful when the LLM provider fails.
        ranked = []
        for index, suggestion in enumerate(suggestions):
            command = _safe_str(suggestion.get("command")).strip()
            repeat_count = recent_counts.get(command.lower(), 0)
            ranked.append((repeat_count, index, suggestion))
        ranked.sort(key=lambda item: (item[0], item[1]))
        first = ranked[0][2]
        command = _safe_str(first.get("command")) or "I carefully observe my surroundings."
        return {
            "ok": True,
            "format_version": PLAYER_AGENT_FORMAT_VERSION,
            "intent": _safe_str(first.get("label")) or "Use suggested action",
            "action": command,
            "reason": "Deterministic fallback selected a suggested action while avoiding recent repetition.",
            "risk": "medium",
            "goal_id": _safe_str(first.get("objective_id")),
            "fallback": True,
            "source_action_id": _safe_str(first.get("action_id")),
        }

    return {
        "ok": True,
        "format_version": PLAYER_AGENT_FORMAT_VERSION,
        "intent": "Observe surroundings",
        "action": "I carefully observe my surroundings for useful details, exits, people, and threats.",
        "reason": "Deterministic fallback because no suggested actions were available.",
        "risk": "low",
        "goal_id": "",
        "fallback": True,
    }


def validate_player_action_against_context(
    *,
    player_action: Dict[str, Any],
    player_action_context: Dict[str, Any],
) -> Dict[str, Any]:
    action = _safe_str(_safe_dict(player_action).get("action"))
    if not action:
        return {"ok": False, "reason": "missing_action"}

    banned_fragments = [
        "i gain ",
        "i receive ",
        "i complete the quest",
        "i kill them instantly",
        "i find 100",
        "the gm gives me",
        "the narrator says",
    ]
    lower = action.lower()
    for fragment in banned_fragments:
        if fragment in lower:
            return {
                "ok": False,
                "reason": "player_action_appears_to_decide_outcome",
                "fragment": fragment,
            }

    return {"ok": True, "reason": "valid_player_action"}