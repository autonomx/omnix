"""Phase 8.0 — UX Payload Builder.

Aggregates outputs from all subsystems into player-facing UX payloads.
This layer does NOT compute truth itself — it reads from existing
authoritative subsystems only.
"""

from __future__ import annotations

import uuid
from typing import Any

from .layout import PanelLayout
from .models import (
    ActionResultPayload,
    PanelDescriptor,
    PlayerChoiceCard,
    SceneUXPayload,
)


class UXPayloadBuilder:
    """Build unified UX payloads from loop subsystem outputs."""

    def __init__(self, layout: PanelLayout | None = None) -> None:
        self._layout = layout or PanelLayout()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def build_scene_payload(self, loop: Any) -> SceneUXPayload:
        """Build a complete scene payload from the current loop state."""
        tick = getattr(loop, "tick_count", None)
        payload_id = f"scene:{tick}" if tick is not None else "scene:unknown"
        scene = self._gather_scene(loop)
        control_output = self._gather_control_output(loop)
        choices = self._build_choice_cards(control_output)
        panels = self._build_panel_descriptors(loop)
        highlights = self._build_highlights(loop)
        interaction = self._build_interaction_payload(loop)

        payload = SceneUXPayload(
            payload_id=payload_id,
            scene=scene,
            choices=choices,
            panels=panels,
            highlights=highlights,
            interaction=interaction,
        )
        payload.trace = {"tick": tick}
        return payload

    def build_action_result_payload(
        self, loop: Any, action_result: dict
    ) -> ActionResultPayload:
        """Build an action-result payload after a choice selection."""
        panels = self._build_panel_descriptors(loop)
        control_output = self._gather_control_output(loop)
        choices = self._build_choice_cards(control_output)
        interaction = self._build_interaction_payload(loop)

        return ActionResultPayload(
            result_id=str(uuid.uuid4()),
            action_result=dict(action_result),
            updated_scene=self._gather_scene(loop),
            updated_choices=choices,
            updated_panels=panels,
            interaction=interaction,
            metadata={
                "choice_id": action_result.get("choice_id"),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_choice_cards(
        self, control_output: dict | None
    ) -> list[PlayerChoiceCard]:
        """Convert control-layer choice set into PlayerChoiceCard list."""
        if not control_output:
            return []
        choice_set = control_output.get("choice_set", {})
        options = choice_set.get("options", [])
        cards: list[PlayerChoiceCard] = []
        for opt in options:
            cards.append(
                PlayerChoiceCard(
                    choice_id=opt.get("option_id", ""),
                    label=opt.get("label", ""),
                    summary=opt.get("summary", opt.get("description", "")),
                    intent_type=opt.get("intent_type", opt.get("type", "")),
                    target_id=opt.get("target_id"),
                    tags=list(opt.get("tags", [])),
                    priority=float(opt.get("priority", 0.0)),
                )
            )
        return sorted(cards, key=lambda c: (-c.priority, c.choice_id))

    def _build_panel_descriptors(self, loop: Any) -> list[PanelDescriptor]:
        """Build panel descriptors reflecting currently available panels."""
        layout = self._layout.build_default_layout()
        filtered: list[PanelDescriptor] = []
        for panel in layout:
            data = None
            if hasattr(loop, "open_panel"):
                try:
                    data = loop.open_panel(panel.panel_id)
                except Exception:
                    data = None

            if data:
                filtered.append(panel)

        if filtered:
            return filtered

        available: dict[str, dict] = {}

        # Journal
        if hasattr(loop, "campaign_memory_core") and loop.campaign_memory_core is not None:
            entries = loop.campaign_memory_core.journal_entries
            available["journal"] = {"count": len(entries)}

        # Recap
        if hasattr(loop, "campaign_memory_core") and loop.campaign_memory_core is not None:
            available["recap"] = {"count": 1 if loop.campaign_memory_core.last_recap else 0}

        # Codex
        if hasattr(loop, "campaign_memory_core") and loop.campaign_memory_core is not None:
            available["codex"] = {"count": len(loop.campaign_memory_core.codex_entries)}

        # Campaign memory
        if hasattr(loop, "campaign_memory_core") and loop.campaign_memory_core is not None:
            available["campaign_memory"] = {
                "count": 1 if loop.campaign_memory_core.last_campaign_snapshot else 0,
            }

        # Social
        if hasattr(loop, "social_state_core") and loop.social_state_core is not None:
            available["social"] = {}

        # Arcs
        if hasattr(loop, "arc_control_controller") and loop.arc_control_controller is not None:
            available["arc"] = {"count": len(loop.arc_control_controller.arcs)}

        # Reveals
        if hasattr(loop, "arc_control_controller") and loop.arc_control_controller is not None:
            available["reveals"] = {"count": len(loop.arc_control_controller.reveals)}

        # Packs
        if hasattr(loop, "pack_registry") and loop.pack_registry is not None:
            available["packs"] = {"count": len(loop.pack_registry.list_packs())}

        # Scene bias
        if hasattr(loop, "arc_control_controller") and loop.arc_control_controller is not None:
            available["scene_bias"] = {
                "count": len(loop.arc_control_controller.scene_biases),
            }

        return self._layout.build_player_layout(available)

    def _build_highlights(self, loop: Any) -> dict:
        """Build structured highlights for the scene payload."""
        coherence = getattr(loop, "coherence_core", None)
        arc = getattr(loop, "arc_control_controller", None)

        return {
            "location": getattr(loop, "current_location", None),
            "active_threads": len(coherence.query.get_active_threads()) if coherence else 0,
            "top_arc": next(iter(arc.arcs.keys()), None) if arc else None,
            "has_pending_reveals": bool(arc.reveals) if arc else False,
        }

    @staticmethod
    def _gather_scene(loop: Any) -> dict:
        """Read the current scene dict from the loop."""
        if hasattr(loop, "coherence_core") and loop.coherence_core is not None:
            return loop.coherence_core.get_scene_summary()
        return {}

    @staticmethod
    def _gather_control_output(loop: Any) -> dict | None:
        """Read the last control output from the loop."""
        controller = getattr(loop, "gameplay_control_controller", None)
        if controller is not None:
            choice_set = controller.get_last_choice_set()
            if choice_set is not None:
                return {"choice_set": choice_set}
        return None

    # ------------------------------------------------------------------
    # Phase 8.1 — Interaction payload
    # ------------------------------------------------------------------

    @staticmethod
    def _build_interaction_payload(loop: Any) -> dict:
        """Read the latest dialogue response from the loop, if present."""
        response = getattr(loop, "last_dialogue_response", None)
        if response and isinstance(response, dict):
            return dict(response)
        return {}