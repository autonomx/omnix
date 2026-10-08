"""Phase 7.8 — Scene Bias Controller.

Scene/type biasing and live steering flags.  This controller
reorders/annotates choices and adds focus hints to the director
context.  It does **not** mutate truth.
"""

from __future__ import annotations


from .models import SceneBiasState


class SceneBiasController:
    """Manage scene-type biasing and live steering flags."""

    def get(
        self, state: dict[str, SceneBiasState], bias_id: str
    ) -> SceneBiasState | None:
        """Return a single bias entry by ID, or ``None``."""
        return state.get(bias_id)

    def get_active_bias(
        self, state: dict[str, SceneBiasState]
    ) -> SceneBiasState | None:
        """Return the most recently inserted bias, or ``None``."""
        if not state:
            return None
        return next(reversed(state.values()), None)

