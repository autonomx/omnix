"""Phase 7.5 — Crowd State Builder.

Derive current crowd/social atmosphere in the scene.
"""

from __future__ import annotations

from typing import Any

from .models import CrowdStateView


class CrowdStateBuilder:
    """Build a snapshot of the crowd/social atmosphere from coherence."""

    def build(self, coherence_core: Any) -> CrowdStateView:
        """Build a CrowdStateView from the current coherence state."""
        return CrowdStateView(
            mood=self._derive_mood(coherence_core),
            tension=self._derive_tension(coherence_core),
            support_level=self._derive_support_level(coherence_core),
            present_npc_ids=self._present_npcs(coherence_core),
        )

    def _derive_mood(self, coherence_core: Any) -> str:
        """Derive the crowd mood from scene state.

        Simple heuristic: if there are active tensions, mood is 'uneasy';
        otherwise 'neutral'.
        """
        try:
            state = coherence_core.get_state()
            anchors = getattr(state, "scene_anchors", [])
            if anchors:
                latest = anchors[-1]
                tensions = (
                    latest.get("active_tensions", [])
                    if isinstance(latest, dict)
                    else getattr(latest, "active_tensions", [])
                )
                if tensions:
                    return "uneasy"
        except (AttributeError, TypeError, IndexError):
            pass
        return "neutral"

    def _derive_tension(self, coherence_core: Any) -> str:
        """Derive tension level from scene state.

        Simple heuristic based on number of active tensions and
        recent consequences.
        """
        tension_count = 0
        consequence_count = 0
        try:
            state = coherence_core.get_state()
            anchors = getattr(state, "scene_anchors", [])
            if anchors:
                latest = anchors[-1]
                tensions = (
                    latest.get("active_tensions", [])
                    if isinstance(latest, dict)
                    else getattr(latest, "active_tensions", [])
                )
                tension_count = len(tensions)

            consequences = getattr(state, "recent_consequences", [])
            consequence_count = len(consequences)
        except (AttributeError, TypeError, IndexError):
            pass

        total = tension_count + consequence_count
        if total >= 4:
            return "high"
        if total >= 2:
            return "medium"
        return "low"

    def _derive_support_level(self, coherence_core: Any) -> str:
        """Derive support level from scene state.

        Conservative default: 'mixed'.
        """
        # In Phase 7.5, keep this simple — always return 'mixed'
        # until we have richer faction/relationship data to analyze.
        return "mixed"

    def _present_npcs(self, coherence_core: Any) -> list[str]:
        """Get list of present NPC IDs from the scene anchor."""
        try:
            state = coherence_core.get_state()
            anchors = getattr(state, "scene_anchors", [])
            if anchors:
                latest = anchors[-1]
                actors = (
                    latest.get("present_actors", [])
                    if isinstance(latest, dict)
                    else getattr(latest, "present_actors", [])
                )
                return list(actors)
        except (AttributeError, TypeError, IndexError):
            pass
        return []
