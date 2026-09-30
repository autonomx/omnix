"""Stable compatibility facade for canonical RPG runtime narration.

The previous implementation is retained in ``runtime_narration_legacy`` as a
candidate-generation adapter. Final validation, recovery, rendering, rollout,
and publication are owned by the canonical response-generation pipeline.
"""
from __future__ import annotations

from app.rpg.narration import runtime_narration_legacy as _legacy

from app.rpg.response_generation.runtime_bridge import (
    build_runtime_narration_payload as build_runtime_narration_payload,
)


def __getattr__(name: str):
    """Delegate legacy imports to their narration implementation module."""
    try:
        return getattr(_legacy, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


__all__ = ["build_runtime_narration_payload"]
