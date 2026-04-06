"""Phase A — Canonical UI builder package.

Provides deterministic, read-only character and world UI state builders
for presentation-derived character and world inspector panels.
"""
from .character_builder import (
    build_character_inspector_entry,
    build_character_inspector_state,
    build_character_ui_entry,
    build_character_ui_state,
)
from .world_builder import (
    build_faction_inspector_state,
    build_location_inspector_state,
    build_world_inspector_state,
)

__all__ = [
    "build_character_inspector_entry",
    "build_character_inspector_state",
    "build_character_ui_entry",
    "build_character_ui_state",
    "build_faction_inspector_state",
    "build_location_inspector_state",
    "build_world_inspector_state",
]
