"""Phase 7.8 — Scene Bias Controller.

Scene/type biasing and live steering flags.  This controller
reorders/annotates choices and adds focus hints to the director
context.  It does **not** mutate truth.
"""

from __future__ import annotations

from typing import Any

from .models import SceneBiasState


class SceneBiasController:
    """Manage scene-type biasing and live steering flags."""

    def get(
        self, state: dict[str, SceneBiasState], bias_id: str
    ) -> SceneBiasState | None:
        """Return a single bias entry by ID, or ``None``."""
        return state.get(bias_id)

    def set_bias(
        self, state: dict[str, SceneBiasState], bias: SceneBiasState
    ) -> None:
        """Insert or replace a scene-bias entry."""
        state[bias.bias_id] = bias

    def get_active_bias(
        self, state: dict[str, SceneBiasState]
    ) -> SceneBiasState | None:
        """Return the most recently inserted bias, or ``None``."""
        if not state:
            return None
        return next(reversed(state.values()), None)

    def apply_to_choice_set(
        self, bias: SceneBiasState | None, choice_set: dict
    ) -> dict:
        """Annotate a choice-set payload with scene-bias hints.

        Adds a ``"scene_bias"`` section with focus hints.  Does **not**
        remove or replace existing keys.  A defensive copy is made to
        prevent upstream mutation of the original choice_set.
        """
        if bias is None:
            return dict(choice_set)

        # Phase 7.8 tightening — copy before applying bias
        choice_set = dict(choice_set)
        options = list(choice_set.get("options", []))
        options = [dict(o) for o in options]

        hints: dict[str, Any] = {
            "scene_type_bias": bias.scene_type_bias,
            "force_option_framing": bias.force_option_framing,
            "force_recap": bias.force_recap,
        }
        if bias.focus_arc_id:
            hints["focus_arc_id"] = bias.focus_arc_id
        if bias.focus_thread_id:
            hints["focus_thread_id"] = bias.focus_thread_id
        if bias.focus_npc_id:
            hints["focus_npc_id"] = bias.focus_npc_id
        choice_set["options"] = options
        choice_set["scene_bias"] = hints
        return choice_set

    def apply_to_director_context(
        self, bias: SceneBiasState | None, director_context: dict
    ) -> dict:
        """Annotate a director-context payload with scene-bias hints.

        Adds a ``"scene_bias"`` section.  Does **not** replace existing
        context entries.
        """
        if bias is None:
            return director_context
        hints: dict[str, Any] = {
            "scene_type_bias": bias.scene_type_bias,
            "force_option_framing": bias.force_option_framing,
            "force_recap": bias.force_recap,
        }
        if bias.focus_arc_id:
            hints["focus_arc_id"] = bias.focus_arc_id
        if bias.focus_thread_id:
            hints["focus_thread_id"] = bias.focus_thread_id
        if bias.focus_npc_id:
            hints["focus_npc_id"] = bias.focus_npc_id
        output = dict(director_context)
        output["scene_bias"] = hints
        return output
