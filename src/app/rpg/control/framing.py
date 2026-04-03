"""Phase 7.2 — Framing Engine.

Manages framing state (focus, forced recaps, forced option framing) that
biases the option engine and is consumed by the controller each tick.
"""

from __future__ import annotations

from typing import Any

from .models import ChoiceSet, FramingState


class FramingEngine:
    """Tracks and manages framing state that influences player choices."""

    def __init__(self) -> None:
        self._state = FramingState()

    def get_state(self) -> FramingState:
        return self._state

    def set_focus_target(self, target_type: str, target_id: str) -> None:
        """Set a focus target that will bias options toward this entity."""
        self._state.focus_target_type = target_type
        self._state.focus_target_id = target_id

    def clear_focus_target(self) -> None:
        """Clear any existing focus target."""
        self._state.focus_target_type = None
        self._state.focus_target_id = None

    def mark_forced_recap(self) -> None:
        """Flag that a forced recap is pending."""
        self._state.forced_recap_pending = True

    def mark_forced_option_framing(self) -> None:
        """Flag that forced option framing is pending."""
        self._state.forced_option_framing_pending = True

    def consume_forced_recap(self) -> bool:
        """Consume the forced recap flag. Returns True if it was pending."""
        if self._state.forced_recap_pending:
            self._state.forced_recap_pending = False
            return True
        return False

    def consume_forced_option_framing(self) -> bool:
        """Consume the forced option framing flag. Returns True if it was pending."""
        if self._state.forced_option_framing_pending:
            self._state.forced_option_framing_pending = False
            return True
        return False

    def update_from_gm_state(self, gm_state: Any) -> None:
        """Update framing state from GM directives.

        This v1 implementation checks for pending forced recaps
        and option framing directives in the GM state.
        """
        if gm_state is None:
            return

        # Check for forced recap directives
        for directive in gm_state.list_directives() if hasattr(gm_state, 'list_directives') else []:
            if hasattr(directive, 'directive_type'):
                if directive.directive_type == "recap" and getattr(directive, 'force', False):
                    self.mark_forced_recap()
                if directive.directive_type == "option_framing" and getattr(directive, 'force', False):
                    self.mark_forced_option_framing()

    def mark_choice_set_presented(self, choice_set: ChoiceSet, tick: int | None = None) -> None:
        """Record that a choice set was presented to the player."""
        self._state.last_choice_set = choice_set

    def serialize_state(self) -> dict:
        return self._state.to_dict()

    def deserialize_state(self, data: dict) -> None:
        self._state = FramingState.from_dict(data)