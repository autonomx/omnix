from __future__ import annotations

import json
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


VAGUE_ACTION_PATTERNS = (
    "current objective",
    "anything that can help",
    "what they know",
    "grounded way to make progress",
    "make progress on",
    "tell me more",
    "elaborate",
    "what else",
)


def is_vague_player_action(action: str) -> bool:
    lower = _safe_str(action).lower()
    return any(pattern in lower for pattern in VAGUE_ACTION_PATTERNS)


def build_player_reasoning_prompt(context: Dict[str, Any]) -> List[Dict[str, str]]:
    payload = {
        "active_objectives": _safe_list(context.get("active_objectives"))[:6],
        "quest_log_summary": _safe_dict(context.get("quest_log_summary")),
        "known_clues": _safe_list(context.get("known_clues"))[:10],
        "nearby_npcs": _safe_list(context.get("nearby_npcs"))[:8],
        "recent_turns": _safe_list(context.get("recent_turns"))[-8:],
        "suggested_actions": _safe_list(context.get("suggested_actions"))[:10],
        "goal_pressure": _safe_dict(context.get("goal_pressure")),
    }

    system = (
        "You are an intelligent RPG player-agent. "
        "You must choose a clever, concrete next action that advances the game. "
        "Do not roleplay vague conversation. Do not ask generic objective questions. "
        "Reason from objectives, clues, NPCs, and recent failed attempts. "
        "Return JSON only."
    )

    user = (
        "Choose the highest-leverage next action.\n\n"
        "Rules:\n"
        "- Ask specific questions, not vague ones.\n"
        "- If an NPC repeats or deflects, change tactic, target, or location.\n"
        "- Prefer actions that can change quest state, location, service state, or story arc state.\n"
        "- If the objective is to find a witness, ask who saw them, where they went, then inspect that place.\n"
        "- If you have findings, report them to the quest giver.\n"
        "- If the tavern lead is exhausted, leave and follow the road/trail lead.\n\n"
        "CONTEXT_JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n\n"
        "Return exactly:\n"
        "{\n"
        '  "goal": "...",\n'
        '  "current_hypothesis": "...",\n'
        '  "missing_information": "...",\n'
        '  "best_next_action": "...",\n'
        '  "why_this_advances_progress": "...",\n'
        '  "fallback_if_blocked": "..."\n'
        "}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def normalize_player_reasoning_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"best_next_action": payload}
    payload = _safe_dict(payload)

    best = _safe_str(payload.get("best_next_action") or payload.get("action")).strip()
    if not best:
        best = "I pursue the strongest concrete lead tied to the active objective."

    return {
        "goal": _safe_str(payload.get("goal")),
        "current_hypothesis": _safe_str(payload.get("current_hypothesis")),
        "missing_information": _safe_str(payload.get("missing_information")),
        "best_next_action": best,
        "why_this_advances_progress": _safe_str(payload.get("why_this_advances_progress")),
        "fallback_if_blocked": _safe_str(payload.get("fallback_if_blocked")),
        "is_vague": is_vague_player_action(best),
    }


def deterministic_concrete_player_action(context: Dict[str, Any]) -> str:
    objectives = _safe_list(context.get("active_objectives"))
    nearby = _safe_list(context.get("nearby_npcs"))
    npc_names = [
        _safe_str(_safe_dict(row).get("name") or _safe_dict(row).get("npc_id"))
        for row in nearby
    ]
    npc_names = [name for name in npc_names if name]
    main_npc = "Bran" if "Bran" in npc_names else (npc_names[0] if npc_names else "the nearest informed NPC")

    blob = " ".join(str(obj) for obj in objectives).lower()

    if "find" in blob and "witness" in blob:
        return (
            f"I ask {main_npc} specifically where the witness was last seen, "
            "who left through the side door, and then I inspect that exit for tracks."
        )

    if "report" in blob and ("bran" in blob or "findings" in blob or "witness" in blob):
        return (
            "I report my witness findings to Bran clearly and ask which road lead "
            "I should pursue next."
        )

    if "bandit" in blob or "road" in blob:
        return (
            "I leave the tavern and follow the road lead, searching for tracks, "
            "ambush signs, or anyone connected to the bandits."
        )

    return (
        f"I ask {main_npc} one specific question tied to the strongest active lead, "
        "then take the physical action the answer points toward."
    )