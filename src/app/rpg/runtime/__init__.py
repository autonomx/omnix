"""Phase 10.5 — Expressive runtime layer.

Owns deterministic runtime dialogue state used between simulation/narrative
systems and read-only presentation builders.
"""
from .dialogue_runtime import (
    ensure_runtime_state,
    get_runtime_dialogue_state,
    build_runtime_turn_id,
    build_runtime_sequence_id,
    get_runtime_emotion,
    begin_runtime_turn,
    append_runtime_stream_chunk,
    finalize_runtime_turn,
    mark_runtime_turn_interrupted,
    trim_runtime_state,
    build_runtime_turn_sequence,
    choose_runtime_interruptions,
    apply_runtime_interruptions,
    start_runtime_sequence,
    stream_runtime_text_segments,
    update_runtime_emotion,
    decay_runtime_emotions,
    build_runtime_style_tags,
    build_runtime_fallback_text,
)

__all__ = [
    "ensure_runtime_state",
    "get_runtime_dialogue_state",
    "build_runtime_turn_id",
    "build_runtime_sequence_id",
    "get_runtime_emotion",
    "begin_runtime_turn",
    "append_runtime_stream_chunk",
    "finalize_runtime_turn",
    "mark_runtime_turn_interrupted",
    "trim_runtime_state",
    "build_runtime_turn_sequence",
    "choose_runtime_interruptions",
    "apply_runtime_interruptions",
    "start_runtime_sequence",
    "stream_runtime_text_segments",
    "update_runtime_emotion",
    "decay_runtime_emotions",
    "build_runtime_style_tags",
    "build_runtime_fallback_text",
]