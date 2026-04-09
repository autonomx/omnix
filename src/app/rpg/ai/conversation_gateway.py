from __future__ import annotations

from typing import Any, Dict, List

from .conversation_prompt_builder import build_npc_conversation_line_prompt
from .conversation_response_parser import (
    is_valid_conversation_line,
    parse_conversation_line_response,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def generate_recorded_conversation_line(
    llm_gateway: Any,
    conversation: Dict[str, Any],
    speaker_id: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    recent_lines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    prompt = build_npc_conversation_line_prompt(
        conversation,
        speaker_id,
        simulation_state,
        runtime_state,
        recent_lines,
    )
    raw = llm_gateway.generate(prompt) if llm_gateway else ""
    parsed = parse_conversation_line_response(raw)
    if not is_valid_conversation_line(parsed):
        return {}
    return {
        "prompt": prompt,
        "raw": raw,
        "parsed": parsed,
        "source": "llm",
    }
