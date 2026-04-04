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

    def set_plan(
        self, state: dict[str, PacingPlanState], plan: PacingPlanState
    ) -> None:
        """Insert or replace a pacing plan."""
        state[plan.plan_id] = plan

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

    def apply_to_control_output(
        self, plan: PacingPlanState | None, control_output: dict
    ) -> dict:
        """Annotate a control-output payload with pacing bias hints.

        This does *not* remove or replace keys — it only adds a
        ``"pacing_bias"`` section.
        """
        if plan is None:
            return control_output
        bias = {
            "danger_bias": plan.danger_bias,
            "mystery_bias": plan.mystery_bias,
            "social_bias": plan.social_bias,
            "combat_bias": plan.combat_bias,
            "target_scene_count": plan.target_scene_count,
            "plan_id": plan.plan_id,
            "label": plan.label,
        }
        output = dict(control_output)
        output["pacing_bias"] = bias
        return output
