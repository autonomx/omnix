"""Phase 7.7 — Recap Builder.

Generate short-form recap snapshots grounded in actual game state.
This is a read-model builder — it derives from authoritative state
and must never mutate coherence or social state.
"""

from __future__ import annotations

from typing import Any

from .models import RecapSnapshot


class RecapBuilder:
    """Generate short-form recap snapshots from current state."""

    def build(
        self,
        coherence_core: Any,
        social_state_core: Any | None = None,
        creator_canon_state: Any | None = None,
        tick: int | None = None,
    ) -> RecapSnapshot:
        """Build a recap snapshot from current authoritative state."""
        scene_summary = coherence_core.get_scene_summary()
        active_threads = coherence_core.get_unresolved_threads()
        recent_consequences = coherence_core.get_recent_consequences(limit=5)
        social_highlights = self._social_highlights(social_state_core)
        summary = self._build_summary(coherence_core, social_state_core)

        tick_part = str(tick) if tick is not None else "latest"
        return RecapSnapshot(
            snapshot_id=f"recap:{tick_part}",
            tick=tick,
            title="Session Recap",
            summary=summary,
            scene_summary=scene_summary,
            active_threads=active_threads,
            recent_consequences=recent_consequences,
            social_highlights=social_highlights,
        )

    def _build_summary(
        self,
        coherence_core: Any,
        social_state_core: Any | None,
    ) -> str:
        """Build a concise text summary from state."""
        parts: list[str] = []
        scene = coherence_core.get_scene_summary()
        location = scene.get("location")
        if location:
            parts.append(f"Current location: {location}.")

        threads = coherence_core.get_unresolved_threads()
        if threads:
            thread_titles = [t.get("title", "unknown") for t in threads[:3]]
            parts.append(f"Active threads: {', '.join(thread_titles)}.")

        consequences = coherence_core.get_recent_consequences(limit=3)
        if consequences:
            c_summaries = [c.get("summary", "") for c in consequences if c.get("summary")]
            if c_summaries:
                parts.append(f"Recent events: {'; '.join(c_summaries[:3])}.")

        if social_state_core is not None:
            state = social_state_core.get_state()
            active_rumors = [r for r in state.rumors.values() if r.active]
            if active_rumors:
                parts.append(f"{len(active_rumors)} active rumor(s) circulating.")

        return " ".join(parts) if parts else "No notable events yet."

    def _social_highlights(self, social_state_core: Any | None) -> list[dict]:
        """Extract social highlights from social state."""
        if social_state_core is None:
            return []

        highlights: list[dict] = []
        state = social_state_core.get_state()

        # Active rumors
        for rumor in state.rumors.values():
            if rumor.active:
                highlights.append({
                    "type": "rumor",
                    "summary": rumor.summary,
                    "subject_id": rumor.subject_id,
                })

        # Notable relationships (high hostility or trust)
        for rel in state.relationships.values():
            if abs(rel.trust) >= 0.5 or abs(rel.hostility) >= 0.5:
                highlights.append({
                    "type": "relationship",
                    "source_id": rel.source_id,
                    "target_id": rel.target_id,
                    "trust": rel.trust,
                    "hostility": rel.hostility,
                })

        return highlights
