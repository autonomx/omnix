"""Phase 8.0 — UX Core Façade.

Central entry point for the player-facing UX layer.
Composes PanelLayout, UXPayloadBuilder, UXActionFlow, and UXPresenter
into a single façade used by GameLoop and external consumers.
"""

from __future__ import annotations

from typing import Any

from .action_flow import UXActionFlow
from .layout import PanelLayout
from .payload_builder import UXPayloadBuilder
from .presenters import UXPresenter


class UXCore:
    """Single UX-layer entry point.

    This class is stateless — it delegates all truth queries to the
    loop and its subsystems.
    """

    def __init__(self) -> None:
        self.layout = PanelLayout()
        self.payload_builder = UXPayloadBuilder(layout=self.layout)
        self.action_flow = UXActionFlow(payload_builder=self.payload_builder)
        self.presenter = UXPresenter()

    # ------------------------------------------------------------------
    # Scene
    # ------------------------------------------------------------------

    def build_scene_payload(self, loop: Any) -> dict:
        """Build and present a unified scene payload."""
        raw = self.payload_builder.build_scene_payload(loop)
        return self.presenter.present_scene_payload(raw.to_dict())

    # ------------------------------------------------------------------
    # Action result
    # ------------------------------------------------------------------

    def build_action_result_payload(
        self, loop: Any, action_result: dict
    ) -> dict:
        """Build and present an action-result payload."""
        raw = self.payload_builder.build_action_result_payload(loop, action_result)
        return self.presenter.present_action_result_payload(raw.to_dict())

    # ------------------------------------------------------------------
    # Choice selection
    # ------------------------------------------------------------------

    def select_choice(self, loop: Any, choice_id: str) -> dict:
        """Select a choice through the action flow and present the result."""
        raw = self.action_flow.select_choice(loop, choice_id)
        return self.presenter.present_action_result_payload(raw)

    # ------------------------------------------------------------------
    # Panel
    # ------------------------------------------------------------------

    def open_panel(self, loop: Any, panel_id: str) -> dict:
        """Open a named panel via the action flow."""
        return self.action_flow.open_panel(loop, panel_id)

    # ------------------------------------------------------------------
    # Recap
    # ------------------------------------------------------------------

    def request_recap(self, loop: Any) -> dict:
        """Request the recap panel."""
        return self.action_flow.request_recap(loop)
