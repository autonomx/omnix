"""Phase 7.3 — Scene Transition Builder.

Builds explicit scene transitions when an action changes the scene.
Mainly for traceability and downstream scene execution clarity.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import SceneTransition


class SceneTransitionBuilder:
    """Build SceneTransition records from mapped action descriptors."""

    def build(
        self, mapped_action: dict, coherence_core: Any
    ) -> Optional[SceneTransition]:
        resolution_type = mapped_action.get("resolution_type", "")
        if resolution_type == "location_travel":
            return self._build_location_transition(mapped_action, coherence_core)
        return None

    # ------------------------------------------------------------------
    # Private builders
    # ------------------------------------------------------------------

    def _build_location_transition(
        self, mapped_action: dict, coherence_core: Any
    ) -> Optional[SceneTransition]:
        target_id = mapped_action.get("target_id")
        if not target_id:
            return None

        from_location: Optional[str] = None
        try:
            scene = coherence_core.get_scene_summary()
            if isinstance(scene, dict):
                from_location = scene.get("location")
        except Exception:
            pass

        return SceneTransition(
            transition_id=f"transition:{from_location or 'unknown'}:{target_id}",
            transition_type="location_travel",
            from_location=from_location,
            to_location=target_id,
            summary=f"Travel from {from_location or 'unknown'} to {target_id}",
        )
