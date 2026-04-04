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
        scene = self._gather_scene(loop)
        control_output = self._gather_control_output(loop)
        choices = self._build_choice_cards(control_output)
        panels = self._build_panel_descriptors(loop)
        highlights = self._build_highlights(loop)

        return SceneUXPayload(
            payload_id=str(uuid.uuid4()),
            scene=scene,
            choices=choices,
            panels=panels,
            highlights=highlights,
        )

    def build_action_result_payload(
        self, loop: Any, action_result: dict
    ) -> ActionResultPayload:
        """Build an action-result payload after a choice selection."""
        panels = self._build_panel_descriptors(loop)
        control_output = self._gather_control_output(loop)
        choices = self._build_choice_cards(control_output)

        return ActionResultPayload(
            result_id=str(uuid.uuid4()),
            action_result=dict(action_result),
            updated_scene=self._gather_scene(loop),
            updated_choices=choices,
            updated_panels=panels,
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
        return cards

    def _build_panel_descriptors(self, loop: Any) -> list[PanelDescriptor]:
        """Build panel descriptors reflecting currently available panels."""
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
        """Build a highlights dict for the scene payload."""
        highlights: dict[str, Any] = {}

        # Active threads count
        if hasattr(loop, "coherence_core") and loop.coherence_core is not None:
            threads = loop.coherence_core.active_threads
            highlights["active_threads_count"] = len(threads) if threads else 0

        # Current location
        if hasattr(loop, "coherence_core") and loop.coherence_core is not None:
            scene_summary = loop.coherence_core.get_scene_summary()
            highlights["current_location"] = scene_summary.get("location")

        # Top arc
        if hasattr(loop, "arc_control_controller") and loop.arc_control_controller is not None:
            arcs = loop.arc_control_controller.arcs
            if arcs:
                first_arc = next(iter(arcs.values()))
                highlights["top_arc"] = first_arc.arc_id if hasattr(first_arc, "arc_id") else None
            else:
                highlights["top_arc"] = None

        # Social warning
        if hasattr(loop, "social_state_core") and loop.social_state_core is not None:
            state = loop.social_state_core.get_state()
            # Flag if any relationship is at negative trust
            warnings = []
            for rel in state.relationships.values():
                if hasattr(rel, "trust") and rel.trust < 0:
                    warnings.append(rel.to_dict() if hasattr(rel, "to_dict") else str(rel))
            highlights["social_warning"] = warnings[0] if warnings else None

        # Due reveals count
        if hasattr(loop, "arc_control_controller") and loop.arc_control_controller is not None:
            reveals = loop.arc_control_controller.reveals
            due = [r for r in reveals.values() if hasattr(r, "status") and r.status == "due"]
            highlights["due_reveals_count"] = len(due)

        return highlights

    @staticmethod
    def _gather_scene(loop: Any) -> dict:
        """Read the current scene dict from the loop."""
        if hasattr(loop, "coherence_core") and loop.coherence_core is not None:
            return loop.coherence_core.get_scene_summary()
        return {}

    @staticmethod
    def _gather_control_output(loop: Any) -> dict | None:
        """Read the last control output from the loop."""
        if hasattr(loop, "gameplay_control_controller"):
            choice_set = loop.gameplay_control_controller.get_last_choice_set()
            if choice_set is not None:
                return {"choice_set": choice_set}
        return None
