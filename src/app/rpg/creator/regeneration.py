"""Targeted regeneration helpers for Creator UX partial refresh flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RegenerationTarget = Literal[
    "factions",
    "locations",
    "npc_seeds",
    "opening",
    "threads",
]

REGENERATION_TARGETS: set[str] = {
    "factions",
    "locations",
    "npc_seeds",
    "opening",
    "threads",
}


@dataclass
class RegenerationOptions:
    target: RegenerationTarget
    replace: bool = True
    preserve_ids: bool = True
    extra_context: dict[str, Any] = field(default_factory=dict)