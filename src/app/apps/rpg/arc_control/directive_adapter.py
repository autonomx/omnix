"""Phase 7.8 — Directive Adapter.

Translates creator/GM directives into arc-control state changes.
This is the bridge between existing GM directives (Phase 7.0/7.1/7.2)
and the new arc steering state.
"""

from __future__ import annotations

from typing import Any

from .models import (
    NarrativeArc,
    PacingPlanState,
    RevealDirectiveState,
    SceneBiasState,
)


class ArcDirectiveAdapter:
    """Bridge GM directives into arc-control state changes."""

    def ingest_gm_state(
        self,
        gm_state: Any,
        arc_state: dict[str, NarrativeArc],
        reveal_state: dict[str, RevealDirectiveState],
        pacing_state: dict[str, PacingPlanState],
        bias_state: dict[str, SceneBiasState],
    ) -> None:
        """Read all active GM directives and update arc-control state."""
        if gm_state is None:
            return

        directives = (
            gm_state.list_directives()
            if hasattr(gm_state, "list_directives")
            else []
        )

        for directive in directives:
            dtype = getattr(directive, "directive_type", None)
            if dtype is None:
                continue

            d = directive

            if dtype == "pin_thread":
                self._apply_pin_thread(
                    {
                        "thread_id": getattr(d, "thread_id", ""),
                        "priority": getattr(d, "priority", "high"),
                    },
                    arc_state,
                )
            elif dtype == "reveal":
                self._apply_reveal_directive(
                    {
                        "reveal_type": getattr(d, "reveal_type", ""),
                        "target_id": getattr(d, "target_id", ""),
                        "timing": getattr(d, "timing", "soon"),
                    },
                    reveal_state,
                )
            elif dtype == "danger":
                self._apply_tone_or_danger(
                    {"level": getattr(d, "level", "medium"), "kind": "danger"},
                    pacing_state,
                )
            elif dtype == "tone":
                self._apply_tone_or_danger(
                    {"tone": getattr(d, "tone", "neutral"), "kind": "tone"},
                    pacing_state,
                )
            elif dtype in ("target_npc", "target_faction", "target_location"):
                self._apply_focus_directive(
                    {
                        "dtype": dtype,
                        "entity_id": getattr(d, "npc_id", "")
                        or getattr(d, "faction_id", "")
                        or getattr(d, "location_id", ""),
                    },
                    bias_state,
                )
            elif dtype == "option_framing":
                self._apply_option_framing(
                    {"force": getattr(d, "force", True)},
                    bias_state,
                )
            elif dtype == "recap":
                self._apply_recap(
                    {"force": getattr(d, "force", True)},
                    bias_state,
                )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_pin_thread(
        self,
        directive: dict,
        arc_state: dict[str, NarrativeArc],
    ) -> None:
        thread_id = directive.get("thread_id", "")
        if not thread_id:
            return
        arc_id = f"arc:{thread_id}"
        if arc_id in arc_state:
            arc_state[arc_id].priority = directive.get("priority", "high")
            arc_state[arc_id].status = "active"
        else:
            arc_state[arc_id] = NarrativeArc(
                arc_id=arc_id,
                title=thread_id,
                status="active",
                priority=directive.get("priority", "high"),
                related_thread_ids=[thread_id],
            )

    def _apply_reveal_directive(
        self,
        directive: dict,
        reveal_state: dict[str, RevealDirectiveState],
    ) -> None:
        reveal_type = directive.get("reveal_type", "")
        target_id = directive.get("target_id", "")
        if not reveal_type or not target_id:
            return
        reveal_id = f"reveal:{reveal_type}:{target_id}"
        reveal_state[reveal_id] = RevealDirectiveState(
            reveal_id=reveal_id,
            target_id=target_id,
            target_type=reveal_type,
            timing=directive.get("timing", "soon"),
        )

    def _apply_tone_or_danger(
        self,
        directive: dict,
        pacing_state: dict[str, PacingPlanState],
    ) -> None:
        plan_id = "gm:pacing"
        existing = pacing_state.get(plan_id)
        if existing is None:
            existing = PacingPlanState(plan_id=plan_id, label="GM pacing")
            pacing_state[plan_id] = existing

        kind = directive.get("kind", "")
        if kind == "danger":
            existing.danger_bias = directive.get("level", "medium")
        elif kind == "tone":
            # Map tone labels to bias adjustments
            tone = directive.get("tone", "neutral")
            if tone in ("dark", "darker", "grim"):
                existing.danger_bias = "high"
            elif tone in ("light", "lighter", "cheerful"):
                existing.danger_bias = "low"

    def _apply_focus_directive(
        self,
        directive: dict,
        bias_state: dict[str, SceneBiasState],
    ) -> None:
        entity_id = directive.get("entity_id", "")
        if not entity_id:
            return
        bias_id = "gm:focus"
        existing = bias_state.get(bias_id)
        if existing is None:
            existing = SceneBiasState(bias_id=bias_id)
            bias_state[bias_id] = existing

        dtype = directive.get("dtype", "")
        if dtype == "target_npc":
            existing.focus_npc_id = entity_id
        elif dtype == "target_faction":
            # Store as metadata — no dedicated field for faction focus
            existing.metadata["focus_faction_id"] = entity_id
        elif dtype == "target_location":
            existing.metadata["focus_location_id"] = entity_id

    def _apply_option_framing(
        self,
        directive: dict,
        bias_state: dict[str, SceneBiasState],
    ) -> None:
        bias_id = "gm:focus"
        existing = bias_state.get(bias_id)
        if existing is None:
            existing = SceneBiasState(bias_id=bias_id)
            bias_state[bias_id] = existing
        existing.force_option_framing = directive.get("force", True)

    def _apply_recap(
        self,
        directive: dict,
        bias_state: dict[str, SceneBiasState],
    ) -> None:
        bias_id = "gm:focus"
        existing = bias_state.get(bias_id)
        if existing is None:
            existing = SceneBiasState(bias_id=bias_id)
            bias_state[bias_id] = existing
        existing.force_recap = directive.get("force", True)
