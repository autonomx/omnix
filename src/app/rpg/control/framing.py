"""Decide whether the next output should emphasize recap, options, focus target, or progression."""

from __future__ import annotations

from typing import Any

from .models import ChoiceSet, FramingState


class FramingEngine:
    """Lightweight control state for scene framing decisions."""

    def __init__(self) -> None:
        self._state = FramingState()

    def get_state(self) -> FramingState:
        return self._state

    def set_state(self, state: FramingState) -> None:
        self._state = state

    def update_from_gm_state(self, gm_state: Any) -> None:
        if gm_state is None:
            return

        if hasattr(gm_state, "has_forced_option_framing") and gm_state.has_forced_option_framing():
            self._state.forced_option_framing_pending = True

        if hasattr(gm_state, "has_forced_recap") and gm_state.has_forced_recap():
            self._state.forced_recap_pending = True

        focus = None
        if hasattr(gm_state, "get_focus_target"):
            focus = gm_state.get_focus_target()
        if focus:
            self._state.focus_target_type = focus.get("target_type")
            self._state.focus_target_id = focus.get("target_id")
        else:
            self._state.focus_target_type = None
            self._state.focus_target_id = None

    def mark_choice_set_presented(self, choice_set: ChoiceSet, tick: int | None = None) -> None:
        self._state.last_choice_set = choice_set.to_dict()
        if tick is not None:
            self._state.last_recap_tick = tick

    def consume_forced_recap(self) -> bool:
        if self._state.forced_recap_pending:
            self._state.forced_recap_pending = False
            return True
        return False

    def consume_forced_option_framing(self) -> bool:
        if self._state.forced_option_framing_pending:
            self._state.forced_option_framing_pending = False
            return True
        return False

    def serialize_state(self) -> dict:
        return self._state.to_dict()

    def deserialize_state(self, data: dict) -> None:
        self._state = FramingState.from_dict(data)
