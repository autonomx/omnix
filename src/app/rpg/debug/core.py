"""Phase 8.4 — Debug Core.

Orchestration façade for the debug/analytics/GM-inspection layer.
Stateless or near-stateless.  Central entry point for Phase 8.4.

This layer consumes traces — it does not create new truth.
"""

from __future__ import annotations

from typing import Any

from .models import GMInspectionBundle
from .presenter import DebugPresenter
from .trace_builder import DebugTraceBuilder


class DebugCore:
    """Central entry point for Phase 8.4 debug/analytics.

    Orchestrates :class:`DebugTraceBuilder` and :class:`DebugPresenter`
    to produce presenter-safe debug payloads.

    This class is stateless — it holds no mutable game state and performs
    no mutations on any subsystem.
    """

    def __init__(self) -> None:
        self._builder = DebugTraceBuilder()
        self._presenter = DebugPresenter()

    # ------------------------------------------------------------------
    # Choice debug
    # ------------------------------------------------------------------

    def build_choice_debug_payload(
        self, control_output: dict, tick: int | None = None
    ) -> dict:
        """Build a presenter-safe choice debug payload."""
        trace = self._builder.build_choice_trace(control_output, tick=tick)
        return self._presenter.present_trace(trace)

    # ------------------------------------------------------------------
    # Action debug
    # ------------------------------------------------------------------

    def build_action_debug_payload(
        self, action_result: dict, tick: int | None = None
    ) -> dict:
        """Build a presenter-safe action debug payload."""
        trace = self._builder.build_action_trace(action_result, tick=tick)
        return self._presenter.present_trace(trace)

    # ------------------------------------------------------------------
    # GM inspection bundle
    # ------------------------------------------------------------------

    def build_gm_inspection_bundle(
        self,
        tick: int | None = None,
        scene_payload: dict | None = None,
        action_result: dict | None = None,
        control_output: dict | None = None,
        last_dialogue_response: dict | None = None,
        last_dialogue_trace: dict | None = None,
        last_encounter_resolution: dict | None = None,
        last_encounter_state: dict | None = None,
        last_world_sim_result: dict | None = None,
        last_world_sim_state: dict | None = None,
        arc_debug_summary: dict | None = None,
        recovery_debug_summary: dict | None = None,
        pack_debug_summary: dict | None = None,
    ) -> dict:
        """Build a full GM inspection bundle and return presenter-safe dict.

        All parameters are optional.  Missing data results in empty
        sections — never fabricated explanations.
        """
        bundle = self._builder.build_gm_bundle(
            tick=tick,
            scene_payload=scene_payload,
            action_result=action_result,
            control_output=control_output,
            last_dialogue_response=last_dialogue_response,
            last_dialogue_trace=last_dialogue_trace,
            last_encounter_resolution=last_encounter_resolution,
            last_encounter_state=last_encounter_state,
            last_world_sim_result=last_world_sim_result,
            last_world_sim_state=last_world_sim_state,
            arc_debug_summary=arc_debug_summary,
            recovery_debug_summary=recovery_debug_summary,
            pack_debug_summary=pack_debug_summary,
        )
        return self._presenter.present_gm_bundle(bundle)

    # ------------------------------------------------------------------
    # System debug snapshot
    # ------------------------------------------------------------------

    def build_system_debug_snapshot(
        self,
        tick: int | None = None,
        control_output: dict | None = None,
        action_result: dict | None = None,
        last_dialogue_response: dict | None = None,
        has_encounter: bool = False,
        world_effect_count: int = 0,
        warning_count: int = 0,
        arc_summary: dict | None = None,
    ) -> dict:
        """Build a quick system-level debug snapshot."""
        choice_count = 0
        if control_output:
            choice_set = control_output.get("choice_set", {})
            choice_count = len(choice_set.get("options", []))

        has_dialogue = bool(last_dialogue_response)

        return self._presenter.present_system_summary(
            tick=tick,
            choice_count=choice_count,
            has_dialogue=has_dialogue,
            has_encounter=has_encounter,
            world_effect_count=world_effect_count,
            warning_count=warning_count,
            arc_summary=arc_summary,
        )
