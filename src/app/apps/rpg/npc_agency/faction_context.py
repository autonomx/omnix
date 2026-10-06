"""Phase 7.4 — Faction Context Builder.

Derives NPC faction alignment from coherence facts and creator metadata.
Keeps logic simple and deterministic.
"""

from __future__ import annotations

from typing import Any

from .models import FactionAlignmentView


class FactionContextBuilder:
    """Build a faction alignment snapshot from coherence state."""

    def build(self, npc_id: str, coherence_core: Any) -> FactionAlignmentView:
        """Derive faction alignment for an NPC."""
        faction_id = self._find_npc_faction(npc_id, coherence_core)
        alignment = self._derive_alignment(npc_id, faction_id, coherence_core)
        return FactionAlignmentView(
            npc_id=npc_id,
            faction_id=faction_id,
            alignment=alignment,
        )

    def _find_npc_faction(self, npc_id: str, coherence_core: Any) -> str | None:
        """Look up faction membership from coherence facts."""
        try:
            state = coherence_core.get_state()
            fact_id = f"{npc_id}:faction"
            fact = state.stable_world_facts.get(fact_id)
            if fact is not None:
                value = fact.value if hasattr(fact, "value") else fact.get("value")
                if isinstance(value, str):
                    return value
        except (AttributeError, TypeError):
            pass
        return None

    def _derive_alignment(
        self, npc_id: str, faction_id: str | None, coherence_core: Any
    ) -> str:
        """Derive alignment string from faction membership.

        For now, simply checks if the faction exists in coherence.
        Returns 'neutral' by default.
        """
        if faction_id is None:
            return "neutral"
        try:
            state = coherence_core.get_state()
            faction_fact = state.stable_world_facts.get(f"faction:{faction_id}")
            if faction_fact is not None:
                metadata = (
                    faction_fact.metadata
                    if hasattr(faction_fact, "metadata")
                    else faction_fact.get("metadata", {})
                )
                if isinstance(metadata, dict):
                    alignment = metadata.get("alignment")
                    if alignment:
                        return str(alignment)
            return "aligned"
        except (AttributeError, TypeError):
            return "neutral"
