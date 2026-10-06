"""Phase 7.7 — Campaign Memory Builder.

Build longer-lived campaign memory snapshots from authoritative state.
This is a read-model builder — it derives from coherence, social, and
creator canon state and must never mutate those systems.
"""

from __future__ import annotations

from typing import Any

from .models import CampaignMemorySnapshot


class CampaignMemoryBuilder:
    """Build longer-lived campaign memory snapshots."""

    def build(
        self,
        coherence_core: Any,
        social_state_core: Any | None = None,
        creator_canon_state: Any | None = None,
        tick: int | None = None,
    ) -> CampaignMemorySnapshot:
        """Build a campaign memory snapshot from current authoritative state."""
        scene_summary = coherence_core.get_scene_summary()
        active_threads = coherence_core.get_unresolved_threads()
        resolved = self._resolved_threads(coherence_core)
        consequences = self._major_consequences(coherence_core)
        social = self._social_summary(social_state_core)
        canon = self._canon_summary(creator_canon_state)

        tick_part = str(tick) if tick is not None else "latest"
        return CampaignMemorySnapshot(
            snapshot_id=f"campaign:{tick_part}",
            tick=tick,
            title="Campaign Memory",
            current_scene=scene_summary,
            active_threads=active_threads,
            resolved_threads=resolved,
            major_consequences=consequences,
            social_summary=social,
            canon_summary=canon,
        )

    def _resolved_threads(self, coherence_core: Any) -> list[dict]:
        """Extract resolved threads from coherence state."""
        resolved: list[dict] = []
        state = coherence_core.get_state()
        for thread_id, thread in state.unresolved_threads.items():
            if thread.status == "resolved":
                resolved.append(thread.to_dict())
        return resolved

    def _major_consequences(self, coherence_core: Any) -> list[dict]:
        """Extract major consequences from coherence state."""
        return coherence_core.get_recent_consequences(limit=20)

    def _social_summary(self, social_state_core: Any | None) -> dict:
        """Build a social summary from social state."""
        if social_state_core is None:
            return {}

        state = social_state_core.get_state()
        return {
            "relationship_count": len(state.relationships),
            "active_rumor_count": sum(1 for r in state.rumors.values() if r.active),
            "alliance_count": len(state.alliances),
            "reputation_edge_count": len(state.reputation_edges),
        }

    def _canon_summary(self, creator_canon_state: Any | None) -> dict:
        """Build a canon summary from creator canon state."""
        if creator_canon_state is None:
            return {}

        facts = creator_canon_state.list_facts()
        return {
            "fact_count": len(facts),
            "subjects": sorted(set(f.subject for f in facts)),
        }
