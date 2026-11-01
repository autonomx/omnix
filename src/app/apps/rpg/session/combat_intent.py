from __future__ import annotations


from app.runtime.clock import utc_now

# RPG session runtime responsibility module.
from app.apps.rpg.narration.scene_grounding import (
    _apply_grounded_scene_overlay as _apply_grounded_scene_overlay,
    _derive_grounded_scene_context as _derive_grounded_scene_context,
    _resolve_location_name as _resolve_location_name,
)
from typing import (
    Any as Any, Dict as Dict, List as List,
)


def _utc_now_iso() -> str:
    return utc_now().isoformat()


# ── Phase F — effective world behavior config ─────────────────────────────


# ── Phase 1 — idle tick cadence policy ────────────────────────────────────


# ── Phase 5 — opening-aware runtime metadata ─────────────────────────────


__all__ = [
    "_apply_grounded_scene_overlay",
    "_derive_grounded_scene_context",
    "_resolve_location_name",
    "_utc_now_iso",
]
