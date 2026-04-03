"""Phase 7.2 — Gameplay Control Controller.

Orchestrates the option engine, framing engine, and pacing controller
to produce gameplay control output for each tick.
"""

from __future__ import annotations

from typing import Any

from .framing import FramingEngine
from .models import ChoiceSet
from .option_engine import OptionEngine


class PacingController:
    """Manages pacing state that biases option priorities."""

    def __init__(self) -> None:
        from .models import PacingState
        self._state = PacingState()

    def get_state(self) -> "PacingState":
        return self._state

    def update_from_coherence(self, coherence_core: Any) -> None:
        """Update pacing state from coherence core signals."""
        # Placeholder for future signal extraction
        pass

    def apply_gm_directives(self, gm_state: Any) -> None:
        """Apply GM directives that affect pacing."""
        if gm_state is None:
            return

        for directive in (
            gm_state.list_directives()
            if hasattr(gm_state, "list_directives")
            else []
        ):
            if hasattr(directive, "directive_type"):
                if directive.directive_type == "danger" and hasattr(
                    directive, "level"
                ):
                    self._state.danger_level = directive.level

    def serialize_state(self) -> dict:
        return self._state.to_dict()

    def deserialize_state(self, data: dict) -> None:
        from .models import PacingState
        self._state = PacingState.from_dict(data)


class GameplayControlController:
    """Top-level controller that combines option engine, pacing, and framing."""

    def __init__(
        self,
        option_engine: OptionEngine | None = None,
        pacing_controller: PacingController | None = None,
        framing_engine: FramingEngine | None = None,
    ) -> None:
        self.option_engine = option_engine or OptionEngine()
        self.pacing_controller = pacing_controller or PacingController()
        self.framing_engine = framing_engine or FramingEngine()
        self._mode: str = "live"

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def build_control_output(
        self,
        coherence_core: Any,
        gm_state: Any,
        tick: int | None = None,
    ) -> dict:
        """Build the full control output for the current tick."""

        # --- Update systems ---
        self.pacing_controller.update_from_coherence(coherence_core)
        self.pacing_controller.apply_gm_directives(gm_state)

        self.framing_engine.update_from_gm_state(gm_state)

        # --- Consume one-shot framing flags ---
        forced_option_framing = (
            self.framing_engine.consume_forced_option_framing()
        )
        forced_recap = self.framing_engine.consume_forced_recap()

        # --- Build choice set ---
        choice_set = self.option_engine.build_choice_set(
            coherence_core=coherence_core,
            gm_state=gm_state,
            pacing_state=self.pacing_controller.get_state(),
            framing_state=self.framing_engine.get_state(),
        )

        # --- Inject framing metadata into output ---
        choice_set.metadata.setdefault("framing", {})
        choice_set.metadata["framing"]["forced_option_framing"] = (
            forced_option_framing
        )
        choice_set.metadata["framing"]["forced_recap"] = forced_recap

        # --- Record presentation ---
        self.framing_engine.mark_choice_set_presented(choice_set, tick=tick)

        return {
            "choice_set": choice_set.to_dict(),
            "pacing": self.pacing_controller.get_state().to_dict(),
            "framing": self.framing_engine.get_state().to_dict(),
        }

    def mark_choice_set_presented(
        self, choice_set: dict, tick: int | None = None
    ) -> None:
        """Re-mark a choice set (used for replay / external control)."""
        cs = ChoiceSet.from_dict(dict(choice_set))
        self.framing_engine.mark_choice_set_presented(cs, tick=tick)

    def serialize_state(self) -> dict:
        return {
            "mode": self._mode,
            "pacing": self.pacing_controller.serialize_state(),
            "framing": self.framing_engine.serialize_state(),
        }

    def deserialize_state(self, data: dict) -> None:
        self._mode = data.get("mode", "live")
        self.pacing_controller.deserialize_state(data.get("pacing", {}))
        self.framing_engine.deserialize_state(data.get("framing", {}))