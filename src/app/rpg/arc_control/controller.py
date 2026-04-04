"""Phase 7.8 — Arc Control Controller.

Central owner for arc steering state.  Orchestrates the arc registry,
reveal scheduler, pacing plan controller, scene bias controller, and
the directive adapter.

This is a **steering layer**, not a truth layer:
- It does not override coherence truth directly.
- It does not act as an authority source.
- It biases selection, pacing, framing, and reveal timing.
- All state is serializable and replay-safe.
"""

from __future__ import annotations

from typing import Any

from .arc_registry import ArcRegistry
from .directive_adapter import ArcDirectiveAdapter
from .models import (
    NarrativeArc,
    PacingPlanState,
    RevealDirectiveState,
    SceneBiasState,
)
from .pacing_plan import PacingPlanController
from .reveal_scheduler import RevealScheduler
from .scene_bias import SceneBiasController


class ArcControlController:
    """Central owner for arc steering state."""

    def __init__(self) -> None:
        self.arcs: dict[str, NarrativeArc] = {}
        self.reveals: dict[str, RevealDirectiveState] = {}
        self.pacing_plans: dict[str, PacingPlanState] = {}
        self.scene_biases: dict[str, SceneBiasState] = {}

        self._arc_registry = ArcRegistry()
        self._reveal_scheduler = RevealScheduler()
        self._pacing_plan_controller = PacingPlanController()
        self._scene_bias_controller = SceneBiasController()
        self._directive_adapter = ArcDirectiveAdapter()

        self._mode: str = "live"

    # ------------------------------------------------------------------
    # Mode propagation
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Set replay/live mode."""
        self._mode = mode

    # ------------------------------------------------------------------
    # Refresh from upstream state
    # ------------------------------------------------------------------

    def refresh_from_state(
        self, coherence_core: Any, gm_state: Any
    ) -> None:
        """Refresh arcs from coherence threads and ingest GM directives.

        Call this once per tick, after coherence/social updates and
        before director processing.
        """
        # Phase 7.8 tightening — deterministic refresh pipeline
        # 1. Rebuild structural arcs from coherence
        self._arc_registry.refresh_from_coherence(self.arcs, coherence_core)

        # 2. Apply GM directives (steering overrides)
        self._directive_adapter.ingest_gm_state(
            gm_state,
            arc_state=self.arcs,
            reveal_state=self.reveals,
            pacing_state=self.pacing_plans,
            bias_state=self.scene_biases,
        )

    # ------------------------------------------------------------------
    # Director context
    # ------------------------------------------------------------------

    def build_director_context(self, coherence_core: Any) -> dict:
        """Build a context dict suitable for the narrative director.

        Returns a dict with keys:
        - ``active_arcs``: list of arc dicts for active arcs
        - ``due_reveals``: list of reveal dicts whose timing is due
        - ``active_pacing_plan``: pacing plan dict or ``None``
        - ``active_scene_bias``: scene bias dict or ``None``
        """
        active_arcs = [
            a.to_dict()
            for a in self._arc_registry.list_arcs(self.arcs)
            if a.status == "active"
        ]
        due = [
            r.to_dict()
            for r in self._reveal_scheduler.due_reveals(self.reveals)
        ]
        plan = self._pacing_plan_controller.get_active_plan(self.pacing_plans)
        bias = self._scene_bias_controller.get_active_bias(self.scene_biases)
        return {
            "active_arcs": active_arcs,
            "due_reveals": due,
            "active_pacing_plan": plan.to_dict() if plan else None,
            "active_scene_bias": bias.to_dict() if bias else None,
        }

    # ------------------------------------------------------------------
    # Control-output bias
    # ------------------------------------------------------------------

    def build_control_bias(self, control_output: dict) -> dict:
        """Return a modified control payload annotated with bias metadata."""
        plan = self._pacing_plan_controller.get_active_plan(self.pacing_plans)
        bias = self._scene_bias_controller.get_active_bias(self.scene_biases)

        output = self._pacing_plan_controller.apply_to_control_output(
            plan, control_output
        )
        output = self._scene_bias_controller.apply_to_choice_set(bias, output)
        return output

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def serialize_state(self) -> dict:
        """Return a JSON-safe snapshot of all arc-control state."""
        # Phase 7.8 tightening — defensive copy of arc state
        return {
            "arcs": {k: dict(v.to_dict()) for k, v in self.arcs.items()},
            "reveals": {k: dict(v.to_dict()) for k, v in self.reveals.items()},
            "pacing_plans": {
                k: dict(v.to_dict()) for k, v in self.pacing_plans.items()
            },
            "scene_biases": {
                k: dict(v.to_dict()) for k, v in self.scene_biases.items()
            },
            "mode": self._mode,
        }

    def deserialize_state(self, data: dict) -> None:
        """Restore arc-control state from a serialized snapshot."""
        self.arcs = {
            k: NarrativeArc.from_dict(v)
            for k, v in data.get("arcs", {}).items()
        }
        self.reveals = {
            k: RevealDirectiveState.from_dict(v)
            for k, v in data.get("reveals", {}).items()
        }
        self.pacing_plans = {
            k: PacingPlanState.from_dict(v)
            for k, v in data.get("pacing_plans", {}).items()
        }
        self.scene_biases = {
            k: SceneBiasState.from_dict(v)
            for k, v in data.get("scene_biases", {}).items()
        }
        self._mode = data.get("mode", "live")

    # ------------------------------------------------------------------
    # Phase 7.9 — Pack seed integration
    # ------------------------------------------------------------------

    def load_arc_seed(self, payload: dict) -> None:
        """Upsert arcs, reveals, pacing plans, and biases from a pack seed.

        This is an explicit seed-application path. It does not bypass
        coherence — it populates arc control state for subsequent
        director context building.
        """
        from .models import NarrativeArc, RevealDirectiveState, PacingPlanState

        for arc_data in payload.get("arcs", []):
            if not isinstance(arc_data, dict):
                continue
            arc_id = arc_data.get("arc_id", "")
            if arc_id:
                arc = NarrativeArc.from_dict(arc_data)
                if arc_id in self.arcs:
                    existing = self.arcs[arc_id]
                    existing.title = arc.title or existing.title
                    existing.related_thread_ids = (
                        arc.related_thread_ids or existing.related_thread_ids
                    )
                else:
                    self.arcs[arc_id] = arc

        for reveal_data in payload.get("reveal_seeds", []):
            if not isinstance(reveal_data, dict):
                continue
            reveal_id = reveal_data.get("reveal_id", "")
            if reveal_id:
                self.reveals[reveal_id] = RevealDirectiveState.from_dict(reveal_data)

        for pacing_data in payload.get("pacing_presets", []):
            if not isinstance(pacing_data, dict):
                continue
            plan_id = pacing_data.get("plan_id", "")
            if plan_id:
                self.pacing_plans[plan_id] = PacingPlanState.from_dict(pacing_data)

    # ------------------------------------------------------------------
    # Phase 8.2 — Encounter guidance (read-only)
    # ------------------------------------------------------------------

    def build_encounter_guidance(
        self, encounter_mode: str | None = None
    ) -> dict:
        """Return deterministic encounter-level guidance from arc state.

        This is read-only and does not mutate arc state. The guidance
        can bias encounter resolution, e.g. whether diplomacy cracks
        quickly or investigation yields a breakthrough.
        """
        plan = self._pacing_plan_controller.get_active_plan(self.pacing_plans)
        bias = self._scene_bias_controller.get_active_bias(self.scene_biases)

        guidance: dict = {
            "preferred_pressure": "medium",
            "should_escalate": False,
            "should_delay_resolution": False,
            "stakes_bias": "standard",
            "mode_bias": encounter_mode,
        }

        if plan is not None:
            guidance["preferred_pressure"] = plan.metadata.get(
                "preferred_pressure", "medium"
            )
            guidance["should_escalate"] = plan.metadata.get(
                "should_escalate", False
            )
            guidance["should_delay_resolution"] = plan.metadata.get(
                "should_delay_resolution", False
            )

        if bias is not None:
            guidance["stakes_bias"] = bias.metadata.get(
                "stakes_bias", "standard"
            )

        return guidance

    # ------------------------------------------------------------------
    # Phase 8.3 — World simulation guidance (read-only)
    # ------------------------------------------------------------------

    def build_world_sim_guidance(self) -> dict:
        """Return deterministic world-sim-level guidance from arc state.

        Read-only — does not mutate arc state.  This guidance biases
        world sim deterministically (e.g. pacing slow → pressure rises).
        """
        plan = self._pacing_plan_controller.get_active_plan(self.pacing_plans)
        bias = self._scene_bias_controller.get_active_bias(self.scene_biases)

        active_arcs = [
            a.to_dict()
            for a in self._arc_registry.list_arcs(self.arcs)
            if a.status == "active"
        ]

        guidance: dict = {
            "top_active_arcs": [a.get("arc_id", "") for a in active_arcs[:3]],
            "reveal_pressure": "normal",
            "pacing_pressure": "normal",
            "escalation_bias": "neutral",
            "preferred_thread_pressure_targets": [],
        }

        if plan is not None:
            pacing_meta = plan.metadata or {}
            guidance["pacing_pressure"] = pacing_meta.get(
                "pacing_pressure", "normal"
            )
            guidance["escalation_bias"] = (
                "escalate" if pacing_meta.get("should_escalate") else "neutral"
            )

        due_reveals = list(
            self._reveal_scheduler.due_reveals(self.reveals)
        )
        if due_reveals:
            guidance["reveal_pressure"] = "high"

        if bias is not None:
            targets = bias.metadata.get("preferred_thread_pressure_targets", [])
            if isinstance(targets, list):
                guidance["preferred_thread_pressure_targets"] = targets

        return guidance
