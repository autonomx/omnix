"""Phase 7.8 — Pacing Plan Controller.

Maintains multi-scene pacing intent.  The pacing plan biases scene
generation without overriding coherence truth.  It adds metadata/hints
such as *prefer social scenes*, *increase mystery pressure*, or
*downshift combat*.
"""

from __future__ import annotations

from .models import PacingPlanState


class PacingPlanController:
    """Manage pacing plans that bias scene generation."""

    def get(
        self, state: dict[str, PacingPlanState], plan_id: str
    ) -> PacingPlanState | None:
        """Return a single plan by ID, or ``None``."""
        return state.get(plan_id)

    def get_active_plan(
        self, state: dict[str, PacingPlanState]
    ) -> PacingPlanState | None:
        """Return the first pacing plan found, or ``None``.

        If multiple plans are stored the most recently inserted one wins
        (dict insertion order).  In practice there is usually zero or one
        active plan.
        """
        if not state:
            return None
        # Return the last-inserted plan (Python 3.7+ dict ordering).
        return next(reversed(state.values()), None)

