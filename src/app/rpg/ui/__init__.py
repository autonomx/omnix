"""Phase A — Canonical UI builder package.

Provides deterministic, read-only character UI state builders
for presentation-derived character panels.
"""
from .character_builder import (
    build_character_inspector_entry,
    build_character_inspector_state,
    build_character_ui_entry,
    build_character_ui_state,
)

__all__ = [
    "build_character_inspector_entry",
    "build_character_inspector_state",
    "build_character_ui_entry",
    "build_character_ui_state",
]
