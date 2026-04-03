"""Orchestrate option generation + pacing + framing into a single control output."""

from __future__ import annotations

from typing import Any

from .framing import FramingEngine
from .models import ChoiceSet
from .option_engine import OptionEngine
from .pacing import PacingController


class GameplayControlController:
    """Top-level controller that combines option engine, pacing, and framing."""

    def __init__(
        self,
        option_engine: OptionEngine | None = None,
        pacing_controller: PacingController | None = None,
        framing_engine: FramingEngine | None = None,
    ) -> None:
        self._option_engine = option_engine or OptionEngine()
        self._pacing = pacing_controller or PacingController()
        self._framing = framing_engine or FramingEngine()
        self._mode: str = "live"

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def build_control_output(
        self,
        coherence_core: Any,
        gm_state: Any,
        tick: int | None = None,
    ) -> dict:
        # Update pacing from coherence + GM state
        self._pacing.update_from_coherence(coherence_core)
        self._pacing.apply_gm_directives(gm_state)

        # Update framing from GM state
        self._framing.update_from_gm_state(gm_state)

        # Generate a fresh choice set
        pacing_state = self._pacing.get_state()
        framing_state = self._framing.get_state()
        choice_set = self._option_engine.build_choice_set(
            coherence_core, gm_state, pacing_state, framing_state
        )

        # Record the choice set in framing
        self._framing.mark_choice_set_presented(choice_set, tick=tick)

        return {
            "choice_set": choice_set.to_dict(),
            "pacing": pacing_state.to_dict(),
            "framing": framing_state.to_dict(),
        }

    def mark_choice_set_presented(
        self, choice_set: dict, tick: int | None = None
    ) -> None:
        cs = ChoiceSet.from_dict(dict(choice_set))
        self._framing.mark_choice_set_presented(cs, tick=tick)

    def serialize_state(self) -> dict:
        return {
            "mode": self._mode,
            "pacing": self._pacing.serialize_state(),
            "framing": self._framing.serialize_state(),
        }

    def deserialize_state(self, data: dict) -> None:
        self._mode = data.get("mode", "live")
        if "pacing" in data:
            self._pacing.deserialize_state(data["pacing"])
        if "framing" in data:
            self._framing.deserialize_state(data["framing"])
