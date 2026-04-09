from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def build_npc_conversation_line_prompt(
    conversation: Dict[str, Any],
    speaker_id: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    recent_lines: List[Dict[str, Any]],
) -> str:
    conversation = _safe_dict(conversation)
    topic = _safe_dict(conversation.get("topic"))
    lines_text = "\n".join(
        f'- { _safe_str(line.get("speaker")) }: {_safe_str(line.get("text"))}'
        for line in (recent_lines or [])[-4:]
    )
    return (
        "Write exactly one NPC conversation line as JSON.\n"
        'Schema: {"speaker": "...", "text": "...", "kind": "statement|question|challenge|warning|agreement|interruption"}\n'
        f"Conversation kind: {_safe_str(conversation.get('kind'))}\n"
        f"Topic type: {_safe_str(topic.get('type'))}\n"
        f"Topic summary: {_safe_str(topic.get('summary'))}\n"
        f"Speaker: {_safe_str(speaker_id)}\n"
        f"Recent lines:\n{lines_text}\n"
        "Constraints: one short line only, no narration, no markdown."
    )
