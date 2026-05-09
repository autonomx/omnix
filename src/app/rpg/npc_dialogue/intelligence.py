from __future__ import annotations

import json
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def build_npc_intelligence_prompt(
    *,
    speaker: str,
    player_action: str,
    npc_profile: Dict[str, Any],
    social_state: Dict[str, Any],
    known_facts: List[str],
    recent_lines: List[str],
    active_objectives: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    payload = {
        "speaker": speaker,
        "player_action": player_action,
        "npc_profile": npc_profile,
        "social_state": social_state,
        "known_facts": known_facts[:12],
        "recent_lines": recent_lines[-8:],
        "active_objectives": active_objectives[:6],
    }

    system = (
        "You are an RPG NPC dialogue intelligence layer. "
        "You may only use known_facts and active_objectives. "
        "Do not invent quest facts, rewards, locations, or outcomes. "
        "Respond as the NPC would, based on personality, fear, trust, role, and recent repetition. "
        "If the player's question is vague, redirect them to a specific grounded lead. "
        "Return JSON only."
    )

    user = (
        "Generate one intelligent in-character NPC reply.\n\n"
        "Requirements:\n"
        "- Do not repeat recent_lines.\n"
        "- If the player asks a vague objective question, ask them to be specific or point to a grounded known lead.\n"
        "- If a known fact can help, reveal it in-character.\n"
        "- If the NPC would be afraid, cautious, evasive, or helpful, reflect that.\n"
        "- The line must be 1-3 sentences.\n\n"
        "CONTEXT_JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n\n"
        "Return exactly:\n"
        "{\n"
        '  "intent": "...",\n'
        '  "known_fact_used": "...",\n'
        '  "line": "...",\n'
        '  "next_hook": "..."\n'
        "}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def normalize_npc_intelligence_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"line": payload}

    payload = _safe_dict(payload)
    return {
        "intent": _safe_str(payload.get("intent")),
        "known_fact_used": _safe_str(payload.get("known_fact_used")),
        "line": _safe_str(payload.get("line")),
        "next_hook": _safe_str(payload.get("next_hook")),
    }


def npc_line_is_invalid(line: str, recent_lines: List[str]) -> bool:
    text = " ".join(_safe_str(line).split()).lower()
    if not text:
        return True
    for recent in recent_lines:
        if text == " ".join(_safe_str(recent).split()).lower():
            return True
    forbidden = (
        "as an ai",
        "i cannot",
        "the player",
        "current objective",
        "dialogue:raw_ai_payload",
    )
    return any(term in text for term in forbidden)