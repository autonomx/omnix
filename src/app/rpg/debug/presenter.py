"""Phase 8.4 — Debug Presenter.

Produce UI-safe, GM-safe, and compact debug views.
No logic ownership — presentation only.
"""

from __future__ import annotations

from typing import Any

from .models import (
    ChoiceExplanation,
    DebugTrace,
    GMInspectionBundle,
)


# Bounded output limits
_MAX_CHOICES_IN_SUMMARY = 20
_MAX_WARNINGS_IN_SUMMARY = 15
_MAX_RECOVERY_EVENTS = 10


class DebugPresenter:
    """UI-safe presenter for debug payloads."""

    def present_trace(self, trace: DebugTrace | dict | None) -> dict:
        """Present a DebugTrace as a compact dict.

        Accepts a ``DebugTrace`` instance, a raw dict, or ``None``.
        """
        if trace is None:
            return {}
        if isinstance(trace, DebugTrace):
            data = trace.to_dict()
        else:
            data = dict(trace)

        nodes = data.get("nodes", [])
        return {
            "trace_id": data.get("trace_id", ""),
            "tick": data.get("tick"),
            "scope": data.get("scope", ""),
            "node_count": len(nodes),
            "nodes": [
                {
                    "node_id": n.get("node_id", ""),
                    "node_type": n.get("node_type", ""),
                    "title": n.get("title", ""),
                    "summary": n.get("summary", ""),
                    "reasons": list(n.get("reasons", [])),
                }
                for n in nodes
            ],
            "warnings": list(data.get("warnings", []))[:_MAX_WARNINGS_IN_SUMMARY],
        }

    def present_choice_explanations(
        self,
        explanations: list[ChoiceExplanation] | list[dict],
    ) -> list[dict]:
        """Present choice explanations as compact dicts."""
        result: list[dict] = []
        for expl in explanations[:_MAX_CHOICES_IN_SUMMARY]:
            if isinstance(expl, ChoiceExplanation):
                data = expl.to_dict()
            else:
                data = dict(expl)
            result.append({
                "choice_id": data.get("choice_id", ""),
                "label": data.get("label", ""),
                "source": data.get("source", ""),
                "priority": data.get("priority", ""),
                "reasons": list(data.get("reasons", [])),
                "constraints": list(data.get("constraints", [])),
            })
        return result

    def present_gm_bundle(
        self, bundle: GMInspectionBundle | dict | None
    ) -> dict:
        """Present a GM inspection bundle as a compact dict.

        Returns a useful GM view with scene summary, choices + reasons,
        latest interaction explanation, encounter/world/arc summaries,
        and warnings.
        """
        if bundle is None:
            return {}
        if isinstance(bundle, GMInspectionBundle):
            data = bundle.to_dict()
        else:
            data = dict(bundle)

        # Scene overview
        scene = data.get("scene", {})
        scene_summary: dict[str, Any] = {}
        if scene:
            scene_summary = {
                "location": scene.get("location", scene.get("location_id")),
                "active_threads": scene.get("active_threads", scene.get("thread_count")),
            }

        # Choice explanations
        raw_choices = data.get("choice_explanations", [])
        choices = self.present_choice_explanations(raw_choices)

        # Dialogue
        dialogue = data.get("dialogue_explanation", {})
        dialogue_summary: dict[str, Any] = {}
        if dialogue:
            dialogue_summary = {
                "speaker_id": dialogue.get("speaker_id", ""),
                "act": dialogue.get("act", ""),
                "tone": dialogue.get("tone", ""),
                "stance": dialogue.get("stance", ""),
                "reason_count": len(dialogue.get("reasons", [])),
                "reasons": list(dialogue.get("reasons", []))[:5],
            }

        # Encounter
        encounter = data.get("encounter_explanation", {})
        encounter_summary: dict[str, Any] = {}
        if encounter:
            encounter_summary = {
                "encounter_id": encounter.get("encounter_id"),
                "mode": encounter.get("mode"),
                "outcome_type": encounter.get("outcome_type", ""),
                "reason_count": len(encounter.get("reasons", [])),
                "reasons": list(encounter.get("reasons", []))[:5],
            }

        # World
        world = data.get("world_explanation", {})
        world_summary: dict[str, Any] = {}
        if world:
            world_summary = {
                "sim_tick": world.get("sim_tick", 0),
                "effect_count": len(world.get("effects", [])),
                "pressure_change_count": len(world.get("pressure_changes", [])),
                "reason_count": len(world.get("reasons", [])),
                "reasons": list(world.get("reasons", []))[:5],
            }

        # Arc
        arc = data.get("arc_explanation", {})
        arc_summary: dict[str, Any] = {}
        if arc:
            arc_summary = {
                "active_arc_count": len(arc.get("active_arcs", [])),
                "reveal_pressure": arc.get("reveal_pressure", ""),
                "pacing_pressure": arc.get("pacing_pressure", ""),
            }

        # Recovery
        recovery_events = data.get("recovery_events", [])[:_MAX_RECOVERY_EVENTS]

        # Warnings
        warnings = list(data.get("warnings", []))[:_MAX_WARNINGS_IN_SUMMARY]

        return {
            "tick": data.get("tick"),
            "scene_summary": scene_summary,
            "choices": choices,
            "dialogue_summary": dialogue_summary,
            "encounter_summary": encounter_summary,
            "world_summary": world_summary,
            "arc_summary": arc_summary,
            "recovery_events": recovery_events,
            "warnings": warnings,
        }

    def present_system_summary(
        self,
        tick: int | None = None,
        choice_count: int = 0,
        has_dialogue: bool = False,
        has_encounter: bool = False,
        world_effect_count: int = 0,
        warning_count: int = 0,
        arc_summary: dict | None = None,
    ) -> dict:
        """Return a quick top-level inspection summary."""
        return {
            "tick": tick,
            "choice_count": choice_count,
            "has_dialogue": has_dialogue,
            "has_encounter": has_encounter,
            "world_effect_count": world_effect_count,
            "warning_count": warning_count,
            "arc_summary": dict(arc_summary) if arc_summary else {},
        }
