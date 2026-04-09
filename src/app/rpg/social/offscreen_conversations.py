from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def run_offscreen_conversation_pass(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    rows = runtime_state.setdefault("offscreen_conversation_summaries", [])
    if not isinstance(rows, list):
        rows = []
        runtime_state["offscreen_conversation_summaries"] = rows

    rows.append({
        "tick": int(tick or 0),
        "type": "offscreen_conversation",
        "summary": "Two unseen NPCs discuss recent events.",
    })
    runtime_state["offscreen_conversation_summaries"] = rows[-40:]
    return runtime_state
