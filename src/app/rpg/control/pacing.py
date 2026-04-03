"""Maintain active pacing state and convert creator/GM controls into gameplay pressure."""

from __future__ import annotations

from typing import Any

from .models import PacingState


class PacingController:
    """Active pacing state derived from coherence + GM directives."""

    def __init__(self) -> None:
        self._state = PacingState()

    def get_state(self) -> PacingState:
        return self._state

    def set_state(self, state: PacingState) -> None:
        self._state = state

    def update_from_coherence(self, coherence_core: Any) -> None:
        self._state.reveal_pressure = self._derive_reveal_pressure_from_threads(coherence_core)
        self._state.social_pressure = self._derive_social_pressure_from_commitments(coherence_core)

    def apply_gm_directives(self, gm_state: Any) -> None:
        self._state.danger_level = self._derive_danger_from_directives(gm_state)

    def advance_scene(self) -> None:
        self._state.scene_index += 1

    def serialize_state(self) -> dict:
        return self._state.to_dict()

    def deserialize_state(self, data: dict) -> None:
        self._state = PacingState.from_dict(data)

    # ------------------------------------------------------------------
    # Internal derivation helpers
    # ------------------------------------------------------------------

    def _derive_danger_from_directives(self, gm_state: Any) -> str:
        if gm_state is None:
            return self._state.danger_level
        for directive in gm_state.get_active_directives():
            dtype = getattr(directive, "directive_type", "")
            if dtype == "danger":
                return getattr(directive, "level", "medium")
        return self._state.danger_level

    def _derive_reveal_pressure_from_threads(self, coherence_core: Any) -> str:
        threads = coherence_core.get_unresolved_threads()
        if not isinstance(threads, list):
            return "medium"
        high_count = 0
        for thread in threads:
            if isinstance(thread, dict):
                priority = thread.get("priority", "normal")
            else:
                priority = getattr(thread, "priority", "normal")
            if priority in ("high", "critical"):
                high_count += 1
        if high_count >= 3:
            return "high"
        if high_count >= 1:
            return "medium"
        return "low"

    def _derive_social_pressure_from_commitments(self, coherence_core: Any) -> str:
        state = coherence_core.get_state()
        player_count = len(getattr(state, "player_commitments", {}))
        npc_count = len(getattr(state, "npc_commitments", {}))
        total = player_count + npc_count
        if total >= 5:
            return "high"
        if total >= 2:
            return "medium"
        return "low"
