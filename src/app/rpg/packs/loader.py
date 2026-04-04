"""Phase 7.9 — Pack Loader.

Load packs into runtime-compatible seed payloads.
This is a translation layer, not a mutator.
"""

from __future__ import annotations

from .models import AdventurePack
from .merger import PackMerger


class PackLoader:
    """Load adventure packs into structured seed payloads."""

    def __init__(self) -> None:
        self._merger = PackMerger()

    def load(self, pack: AdventurePack) -> dict:
        """Load a single pack into a seed payload."""
        return {
            "creator_seed": self._to_creator_seed(pack),
            "arc_seed": self._to_arc_seed(pack),
            "social_seed": self._to_social_seed(pack),
            "memory_seed": self._to_memory_seed(pack),
        }

    def load_many(self, packs: list[AdventurePack]) -> dict:
        """Load and merge multiple packs into a single seed payload."""
        if not packs:
            return {
                "creator_seed": {},
                "arc_seed": {},
                "social_seed": {},
                "memory_seed": {},
            }
        merged = self._merger.merge(packs)
        return self.load(merged)

    def _to_creator_seed(self, pack: AdventurePack) -> dict:
        """Extract creator-relevant seeds from a pack."""
        content = pack.content
        return {
            "creator_facts": list(content.creator_facts),
            "setup_templates": list(content.setup_templates),
            "factions": list(content.factions),
            "locations": list(content.locations),
            "npcs": list(content.npcs),
            "threads": list(content.threads),
            "gm_presets": list(content.gm_presets),
            "pacing_presets": list(content.pacing_presets),
            "pack_id": pack.metadata.pack_id,
            "pack_title": pack.metadata.title,
        }

    def _to_arc_seed(self, pack: AdventurePack) -> dict:
        """Extract arc-control seeds from a pack."""
        content = pack.content
        return {
            "arcs": list(content.arcs),
            "reveal_seeds": list(content.reveal_seeds),
            "pacing_presets": list(content.pacing_presets),
            "pack_id": pack.metadata.pack_id,
        }

    def _to_social_seed(self, pack: AdventurePack) -> dict:
        """Extract social-state seeds from a pack."""
        content = pack.content
        return {
            "social_seeds": list(content.social_seeds),
            "factions": list(content.factions),
            "npcs": list(content.npcs),
            "pack_id": pack.metadata.pack_id,
        }

    def _to_memory_seed(self, pack: AdventurePack) -> dict:
        """Extract memory/codex seeds from a pack."""
        content = pack.content
        return {
            "locations": list(content.locations),
            "factions": list(content.factions),
            "npcs": list(content.npcs),
            "threads": list(content.threads),
            "pack_id": pack.metadata.pack_id,
        }
