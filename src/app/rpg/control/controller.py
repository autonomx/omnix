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
        encounter_controller: Any | None = None,
    ) -> None:
        self.option_engine = option_engine or OptionEngine()
        self.pacing_controller = pacing_controller or PacingController()
        self.framing_engine = framing_engine or FramingEngine()
        self.encounter_controller = encounter_controller
        self._mode: str = "live"

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def build_control_output(
        self,
        coherence_core: Any,
        gm_state: Any,
        tick: int | None = None,
        external_bias: dict | None = None,
    ) -> dict:
        """Build the full control output for the current tick.

        Args:
            coherence_core: Canonical coherence state.
            gm_state: GM directive state.
            tick: Current tick number.
            external_bias: Optional external bias dict (Phase 7.8).
                If present, applied after base choice generation to
                annotate the output with steering hints.  Must remain
                deterministic and must not directly mutate coherence.
        """

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

        # --- Phase 8.2: Merge encounter-aware options ---
        enc_ctrl = self.encounter_controller
        if enc_ctrl is not None:
            if enc_ctrl.has_active_encounter():
                enc_ctx = enc_ctrl.build_choice_context(player_id="player", coherence_core=coherence_core)
                if enc_ctx is not None:
                    encounter_options = self._build_active_encounter_options(enc_ctx)
                    choice_set = self._merge_encounter_options_with_standard_options(
                        choice_set, encounter_options,
                    )
            else:
                start_options = self._build_encounter_start_options(coherence_core)
                if start_options:
                    choice_set = self._merge_encounter_options_with_standard_options(
                        choice_set, start_options,
                    )

        # --- Inject framing metadata into output ---
        choice_set.metadata.setdefault("framing", {})
        choice_set.metadata["framing"]["forced_option_framing"] = (
            forced_option_framing
        )
        choice_set.metadata["framing"]["forced_recap"] = forced_recap

        # --- Record presentation ---
        self.framing_engine.mark_choice_set_presented(choice_set, tick=tick)

        output = {
            "choice_set": choice_set.to_dict(),
            "pacing": self.pacing_controller.get_state().to_dict(),
            "framing": self.framing_engine.get_state().to_dict(),
        }

        # --- Phase 7.8: Apply external bias after base generation ---
        if external_bias:
            output["external_bias"] = dict(external_bias)

        return output

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

    # ------------------------------------------------------------------
    # Phase 7.3 — Choice retrieval and selection helpers
    # ------------------------------------------------------------------

    def get_last_choice_set(self) -> dict | None:
        """Return the last presented choice set as a dict, or None."""
        state = self.framing_engine.get_state()
        return state.last_choice_set

    def select_option(self, option_id: str) -> dict | None:
        """Find and return the option dict matching *option_id* from the
        last presented choice set, or ``None`` if not found."""
        choice_set = self.get_last_choice_set()
        if not choice_set:
            return None
        for option in choice_set.get("options", []):
            if option.get("option_id") == option_id:
                return dict(option)
        return None

    # ------------------------------------------------------------------
    # Phase 8.2 — Encounter-aware option helpers
    # ------------------------------------------------------------------

    def _build_encounter_start_options(
        self, coherence_core: Any,
    ) -> list["ChoiceOption"]:
        """Build explicit encounter-start options when no encounter is active.

        Returns ChoiceOption instances with metadata marking their
        encounter mode start.
        """
        from .models import ChoiceOption

        options: list[ChoiceOption] = []
        options.append(ChoiceOption(
            option_id="enc_start_combat",
            label="Engage openly",
            intent_type="attack",
            summary="Initiate open combat.",
            tags=["tactical", "combat", "encounter_start"],
            priority=0.3,
            metadata={"encounter_start": "combat"},
        ))
        options.append(ChoiceOption(
            option_id="enc_start_stealth",
            label="Sneak around the guards",
            intent_type="sneak",
            summary="Try to move through undetected.",
            tags=["tactical", "stealth", "encounter_start"],
            priority=0.3,
            metadata={"encounter_start": "stealth"},
        ))
        options.append(ChoiceOption(
            option_id="enc_start_investigation",
            label="Inspect the scene",
            intent_type="inspect",
            summary="Begin a thorough investigation.",
            tags=["tactical", "investigation", "encounter_start"],
            priority=0.3,
            metadata={"encounter_start": "investigation"},
        ))
        options.append(ChoiceOption(
            option_id="enc_start_diplomacy",
            label="Try to negotiate",
            intent_type="negotiate",
            summary="Attempt diplomatic resolution.",
            tags=["tactical", "diplomacy", "encounter_start"],
            priority=0.3,
            metadata={"encounter_start": "diplomacy"},
        ))
        options.append(ChoiceOption(
            option_id="enc_start_chase",
            label="Pursue the fleeing target",
            intent_type="pursue",
            summary="Give chase to the fleeing target.",
            tags=["tactical", "chase", "encounter_start"],
            priority=0.3,
            metadata={"encounter_start": "chase"},
        ))
        return options

    def _build_active_encounter_options(
        self, enc_ctx: Any,
    ) -> list["ChoiceOption"]:
        """Build tactical options from an active encounter choice context."""
        from .models import ChoiceOption

        mode = enc_ctx.mode or "combat"
        actions = enc_ctx.available_actions or []
        options: list[ChoiceOption] = []
        for action in actions:
            options.append(ChoiceOption(
                option_id=f"enc_{mode}_{action}",
                label=action.replace("_", " ").title(),
                intent_type=action,
                summary=f"{action.replace('_', ' ').title()} ({mode} encounter)",
                tags=["tactical", mode, action],
                priority=0.6,
                metadata={
                    "encounter_action_type": action,
                    "encounter_tags": ["tactical", mode],
                },
            ))
        return options

    @staticmethod
    def _merge_encounter_options_with_standard_options(
        choice_set: "ChoiceSet",
        encounter_options: list["ChoiceOption"],
    ) -> "ChoiceSet":
        """Merge encounter options into an existing ChoiceSet.

        Encounter options are prepended (higher priority). Existing
        options remain but are not removed — the architecture does not
        bypass normal choice model creation.
        """
        merged = list(encounter_options) + list(choice_set.options)
        choice_set.options = merged
        return choice_set