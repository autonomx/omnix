"""Stable compatibility facade for canonical RPG runtime narration.

The previous implementation is retained in ``runtime_narration_legacy`` as a
candidate-generation adapter. Final validation, recovery, rendering, rollout,
and publication are owned by the canonical response-generation pipeline.
"""
from __future__ import annotations

from app.rpg.narration import runtime_narration_legacy as _legacy

for _name, _value in _legacy.__dict__.items():
    if not _name.startswith("__"):
        globals()[_name] = _value

from app.rpg.response_generation.runtime_bridge import build_runtime_narration_payload

__all__ = [name for name in globals() if not name.startswith("__")]
