"""Phase 8.1 — Dialogue Core.

Orchestration façade for dialogue planning, analogous to UXCore.
Remains mostly stateless — composes DialogueContextBuilder,
DialogueResponsePlanner, and DialoguePresenter.

Single Phase 8.1 entry point used by resolver / game loop / UX.
"""

from __future__ import annotations

from typing import Any

from .context_builder import DialogueContextBuilder
from .presenter import DialoguePresenter
from .response_planner import DialogueResponsePlanner


class DialogueCore:
    """Stateless orchestration façade for structured dialogue planning."""

    def __init__(self) -> None:
        self.context_builder = DialogueContextBuilder()
        self.response_planner = DialogueResponsePlanner()
        self.presenter = DialoguePresenter()

    def build_interaction_response(
        self,
        speaker_id: str,
        listener_id: str | None = None,
        coherence_core: Any = None,
        social_state_core: Any = None,
        arc_control_controller: Any = None,
        campaign_memory_core: Any = None,
        resolved_action: Any = None,
        npc_decision: dict | None = None,
        scene_summary: dict | None = None,
        tick: int | None = None,
    ) -> dict:
        """Build a complete dialogue interaction response.

        Returns:
            A dict with three keys:
            - ``response``: player-safe payload
            - ``trace``: structured reasoning (GM-safe)
            - ``log_entry``: memory candidate (or None)
        """
        # 1. Build context
        context = self.context_builder.build_for_interaction(
            speaker_id=speaker_id,
            listener_id=listener_id,
            coherence_core=coherence_core,
            social_state_core=social_state_core,
            arc_control_controller=arc_control_controller,
            resolved_action=resolved_action,
            npc_decision=npc_decision,
            scene_summary=scene_summary,
            tick=tick,
            history_source=campaign_memory_core,
        )

        # 2. Build plan
        plan = self.response_planner.build_plan(context)

        # 3. Present
        response = self.presenter.present_response(plan)
        trace = self.presenter.present_trace(plan)
        log_entry = self.presenter.present_log_entry(plan, tick=tick)

        return {
            "response": response,
            "trace": trace,
            "log_entry": log_entry,
        }
