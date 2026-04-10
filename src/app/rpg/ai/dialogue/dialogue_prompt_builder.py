from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def build_dialogue_prompt(
    npc: Dict[str, Any],
    scene: Dict[str, Any],
    player_state: Dict[str, Any],
    npc_mind: Dict[str, Any],
    player_message: str,
    runtime_state: Optional[Dict[str, Any]] = None,
) -> str:
    npc = _safe_dict(npc)
    scene = _safe_dict(scene)
    player_state = _safe_dict(player_state)
    npc_mind = _safe_dict(npc_mind)

    beliefs = _safe_dict(npc_mind.get("beliefs")).get("player", {})
    goals = _safe_list(npc_mind.get("goals"))[:3]
    last_decision = _safe_dict(npc_mind.get("last_decision"))
    dialogue_state = _safe_dict(player_state.get("dialogue_state"))
    history = _safe_list(dialogue_state.get("history"))[-6:]

    # Inject character length setting
    runtime_state = _safe_dict(runtime_state or player_state.get("runtime_state"))
    settings = _safe_dict(runtime_state.get("settings"))
    rl = settings.get("response_length")
    if isinstance(rl, str) and rl.strip().lower() in ("short", "medium", "long"):
        char_len = rl.strip().lower()
    elif isinstance(rl, dict):
        char_len = _safe_str(
            rl.get("character_length") or rl.get("narrator_length") or "medium"
        ).strip().lower()
    else:
        char_len = "medium"

    char_instruction = {
        "short": "Keep dialogue brief and direct.",
        "medium": "Use natural conversational detail.",
        "long": "Use expressive, personality-rich dialogue.",
    }.get(char_len, "")

    history_lines = []
    for item in history:
        if not isinstance(item, dict):
            continue
        speaker = _safe_str(item.get("speaker")) or "unknown"
        text = _safe_str(item.get("text"))
        if text:
            history_lines.append(f"{speaker}: {text}")

    return f"""
You are generating an RPG NPC dialogue reply.

NPC:
- id: {_safe_str(npc.get("npc_id") or npc.get("id"))}
- name: {_safe_str(npc.get("name"))}
- role: {_safe_str(npc.get("role"))}
- faction_id: {_safe_str(npc.get("faction_id"))}
- location_id: {_safe_str(npc.get("location_id"))}

Scene:
- id: {_safe_str(scene.get("scene_id") or scene.get("id"))}
- title: {_safe_str(scene.get("title"))}
- type: {_safe_str(scene.get("scene_type") or scene.get("type"))}

NPC mind:
- beliefs about player: {beliefs}
- active goals: {goals}
- last decision: {last_decision}

Recent dialogue:
{chr(10).join(history_lines) if history_lines else "(none)"}

Player message:
{player_message}

Return JSON only with keys:
- reply_text: string
- tone: string
- suggested_replies: array of up to 4 short strings
- intent: string

STYLE:
{char_instruction}
""".strip()