"""Phase 10.6 — Provider result to runtime stream adapter."""
from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.runtime.dialogue_runtime import (
    append_runtime_stream_chunk,
    finalize_runtime_turn,
)


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_bool(v: Any) -> bool:
    return bool(v)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def apply_provider_result_to_runtime_turn(
    simulation_state: Dict[str, Any],
    *,
    turn_id: str,
    actor_id: str,
    speaker_id: str = "",
    provider_result: Dict[str, Any],
    allow_emotional_fallback: bool = False,
) -> Dict[str, Any]:
    """Apply a structured provider/replay/fallback result to runtime turn state.

    Rules:
        - stream_events are written in order through append_runtime_stream_chunk
        - finalization always goes through finalize_runtime_turn
        - no direct writes to presentation state
    """
    provider_result = _safe_dict(provider_result)
    turn_id = _safe_str(turn_id)
    actor_id = _safe_str(actor_id)
    speaker_id = _safe_str(speaker_id) or actor_id

    if not turn_id or not actor_id:
        return simulation_state

    stream_events = [
        _safe_dict(v)
        for v in _safe_list(provider_result.get("stream_events"))
        if isinstance(v, dict)
    ]
    stream_events = sorted(
        stream_events,
        key=lambda item: (
            _safe_int(item.get("event_index"), 0),
            _safe_str(item.get("event_type")),
        ),
    )

    for event in stream_events:
        if _safe_str(event.get("event_type") or "text_chunk") != "text_chunk":
            continue
        simulation_state = append_runtime_stream_chunk(
            simulation_state,
            turn_id=turn_id,
            actor_id=actor_id,
            speaker_id=speaker_id,
            text=_safe_str(event.get("text")),
            chunk_index=_safe_int(event.get("event_index"), 0),
            final=_safe_bool(event.get("final")),
        )

    simulation_state = finalize_runtime_turn(
        simulation_state,
        turn_id=turn_id,
        final_text=_safe_str(provider_result.get("output_text")),
        allow_emotional_fallback=_safe_bool(allow_emotional_fallback),
    )
    return simulation_state