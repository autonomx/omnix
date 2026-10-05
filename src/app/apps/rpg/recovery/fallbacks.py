"""Phase 6.5 — Fallback Scene Builder.

Builds safe, player-facing scenes grounded only in coherence summaries and
last-known-good anchors.  No raw exceptions or stack traces appear in output.
"""
from __future__ import annotations

from typing import Any


class FallbackSceneBuilder:
    """Construct fallback scenes for various failure modes."""

    def build_from_last_good_anchor(
        self, anchor: dict, coherence_summary: dict
    ) -> dict:
        """Build a scene grounded in the last known good anchor."""
        location = anchor.get("location") or self._extract_location(coherence_summary)
        threads = self._extract_threads(coherence_summary)
        return self._scene_shape(
            title="Returning to a familiar moment\u2026",
            body=(
                f"You find yourself back at {location or 'a familiar place'}. "
                "The world steadies itself around you."
            ),
            metadata={
                "recovery": True,
                "source": "last_good_anchor",
                "anchor_id": anchor.get("anchor_id"),
                "active_threads": threads,
            },
        )

    def build_from_coherence_summary(self, coherence_summary: dict) -> dict:
        """Build a minimal safe scene from the coherence summary alone."""
        location = self._extract_location(coherence_summary)
        tensions = self._extract_tensions(coherence_summary)
        return self._scene_shape(
            title="The story pauses\u2026",
            body=(
                f"You are at {location or 'an uncertain place'}. "
                "Something lingers in the air."
            ),
            metadata={
                "recovery": True,
                "source": "coherence_summary",
                "tensions": tensions,
            },
        )

    def build_clarification_scene(
        self, player_input: str, coherence_summary: dict
    ) -> dict:
        """Build a scene that asks the player to clarify their intent."""
        location = self._extract_location(coherence_summary)
        return self._scene_shape(
            title="What do you mean?",
            body=(
                f"At {location or 'your current location'}, "
                "the world awaits your next move. "
                "Could you say that differently?"
            ),
            metadata={
                "recovery": True,
                "source": "clarification",
                "original_input": player_input,
            },
        )

    def build_contradiction_recovery_scene(
        self, contradictions: list[dict], coherence_summary: dict
    ) -> dict:
        """Build a scene acknowledging contradictions in the narrative."""
        location = self._extract_location(coherence_summary)
        summaries = [
            c.get("message", "an inconsistency") for c in contradictions[:3]
        ]
        body_lines = [
            f"At {location or 'your current location'}, "
            "the fabric of events shifts unexpectedly."
        ]
        for summary in summaries:
            body_lines.append(f"  \u2022 {summary}")
        body_lines.append("The world realigns itself.")
        return self._scene_shape(
            title="Something feels off\u2026",
            body="\n".join(body_lines),
            metadata={
                "recovery": True,
                "source": "contradiction_recovery",
                "contradiction_count": len(contradictions),
            },
        )

    def build_director_failure_scene(
        self, coherence_summary: dict, reason: str
    ) -> dict:
        """Build a scene when the director fails to produce output."""
        location = self._extract_location(coherence_summary)
        return self._scene_shape(
            title="A lull in the story\u2026",
            body=(
                f"At {location or 'your current location'}, "
                "a brief silence falls. The narrative gathers itself."
            ),
            metadata={
                "recovery": True,
                "source": "director_failure",
                "reason": reason,
            },
        )

    def build_renderer_failure_scene(
        self,
        coherence_summary: dict,
        partial_narrative: dict | None = None,
    ) -> dict:
        """Build a scene when the renderer fails."""
        location = self._extract_location(coherence_summary)
        body = (
            f"At {location or 'your current location'}, "
            "the scene flickers and steadies."
        )
        if partial_narrative and isinstance(partial_narrative, dict):
            hint = partial_narrative.get("summary") or partial_narrative.get("title")
            if hint:
                body += f" ({hint})"
        return self._scene_shape(
            title="The scene reforms\u2026",
            body=body,
            metadata={
                "recovery": True,
                "source": "renderer_failure",
                "has_partial": partial_narrative is not None,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_location(self, coherence_summary: dict) -> str | None:
        if not coherence_summary:
            return None
        scene = coherence_summary.get("scene_summary", {})
        if isinstance(scene, dict):
            return scene.get("location")
        return None

    def _extract_threads(self, coherence_summary: dict) -> list[dict]:
        if not coherence_summary:
            return []
        return coherence_summary.get("unresolved_threads", [])

    def _extract_tensions(self, coherence_summary: dict) -> list[dict]:
        if not coherence_summary:
            return []
        return coherence_summary.get("active_tensions", [])

    def _scene_shape(
        self,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Return a canonical scene dict compatible with normal scene output."""
        meta = metadata or {}
        # Ensure all recovery scenes carry recovery metadata
        meta.setdefault("recovered", True)
        return {
            "scene": body,
            "title": title,
            "options": [],
            "meta": meta,
            "body": body,
            "narrative": {"title": title, "description": body},
            "scene_data": {},
            "metadata": meta,
        }
