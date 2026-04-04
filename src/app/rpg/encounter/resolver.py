"""Phase 8.2 — Encounter Resolver.

Converts a selected resolved action plus current encounter state into an
EncounterResolution.  This is a pure/deterministic logic layer — it does
not own persistent state.

Only returns a non-None result when an active encounter exists or the
action explicitly starts one.
"""

from __future__ import annotations

from typing import Any

from .models import (
    SUPPORTED_ENCOUNTER_MODES,
    EncounterResolution,
    EncounterState,
)


# Tags that signal encounter-start actions
_ENCOUNTER_START_TAGS: dict[str, str] = {
    "attack": "combat",
    "ambush": "combat",
    "sneak": "stealth",
    "hide": "stealth",
    "inspect": "investigation",
    "investigate": "investigation",
    "negotiate": "diplomacy",
    "demand": "diplomacy",
    "flee": "chase",
    "pursue": "chase",
}


class EncounterResolver:
    """Convert resolved actions into encounter-level outcomes."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_action(
        self,
        encounter_state: EncounterState | None,
        resolved_action: Any,
        scene_summary: dict[str, Any],
        coherence_core: Any | None = None,
        social_state_core: Any | None = None,
        arc_control_controller: Any | None = None,
        tick: int | None = None,
    ) -> EncounterResolution | None:
        """Resolve an action within the encounter context.

        Returns ``None`` when the action is not encounter-relevant.
        """
        if encounter_state is None or encounter_state.status != "active":
            return None

        # Extract action metadata
        action_meta = self._extract_action_meta(resolved_action)
        action_type = action_meta.get("encounter_action_type", "")
        mode = encounter_state.mode

        # Dispatch to mode-specific resolver
        if mode == "combat":
            return self._resolve_combat(encounter_state, action_meta, scene_summary, tick)
        elif mode == "stealth":
            return self._resolve_stealth(encounter_state, action_meta, scene_summary, tick)
        elif mode == "investigation":
            return self._resolve_investigation(encounter_state, action_meta, scene_summary, tick)
        elif mode == "diplomacy":
            return self._resolve_diplomacy(encounter_state, action_meta, scene_summary, tick)
        elif mode == "chase":
            return self._resolve_chase(encounter_state, action_meta, scene_summary, tick)

        # Unknown mode — return a minimal continue resolution
        return EncounterResolution(
            encounter_id=encounter_state.encounter_id,
            mode=mode,
            outcome_type="continue",
            trace={"reason": "unknown_mode", "mode": mode},
        )

    # ------------------------------------------------------------------
    # Encounter relevance helper
    # ------------------------------------------------------------------

    @staticmethod
    def detect_encounter_start(option_meta: dict[str, Any]) -> str | None:
        """Return the encounter mode if the option signals a start, else None."""
        # Explicit metadata flag
        explicit = option_meta.get("encounter_start")
        if explicit and explicit in SUPPORTED_ENCOUNTER_MODES:
            return explicit

        # Tag-based detection
        tags = option_meta.get("encounter_tags", option_meta.get("tags", []))
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower in _ENCOUNTER_START_TAGS:
                return _ENCOUNTER_START_TAGS[tag_lower]

        # Intent-based detection
        intent = option_meta.get("intent_type", "")
        if intent in _ENCOUNTER_START_TAGS:
            return _ENCOUNTER_START_TAGS[intent]

        return None

    # ------------------------------------------------------------------
    # Mode-specific resolvers
    # ------------------------------------------------------------------

    def _resolve_combat(
        self,
        state: EncounterState,
        action_meta: dict[str, Any],
        scene_summary: dict[str, Any],
        tick: int | None,
    ) -> EncounterResolution:
        action_type = action_meta.get("encounter_action_type", "strike")
        participant_updates: list[dict[str, Any]] = []
        objective_updates: list[dict[str, Any]] = []
        state_updates: dict[str, Any] = {"advance_turn": True}
        outcome_type = "continue"
        derived_events: list[dict[str, Any]] = []

        target_id = action_meta.get("target_id")

        if action_type in ("strike", "press_advantage"):
            if target_id:
                participant_updates.append(
                    {"entity_id": target_id, "status": "engaged"}
                )
            # Advance objective if defeat-type exists
            for obj in state.objectives:
                if obj.kind == "defeat" and obj.status == "active":
                    new_progress = min(obj.progress + 1, obj.required)
                    update: dict[str, Any] = {
                        "objective_id": obj.objective_id,
                        "progress": new_progress,
                    }
                    if new_progress >= obj.required:
                        update["status"] = "completed"
                        outcome_type = "resolve"
                    objective_updates.append(update)
                    break

            state_updates["mode_state"] = {"momentum": "attacking"}

        elif action_type == "defend":
            state_updates["mode_state"] = {"momentum": "defensive"}

        elif action_type == "withdraw":
            outcome_type = "resolve"
            state_updates["pressure"] = "low"

        elif action_type in ("reposition", "use_cover"):
            state_updates["mode_state"] = {"momentum": "repositioning"}

        journal_payload = self._build_journal_payload(state, action_type, outcome_type, tick)
        trace = self._build_trace(state, action_type, outcome_type, "combat")

        return EncounterResolution(
            encounter_id=state.encounter_id,
            mode="combat",
            outcome_type=outcome_type,
            participant_updates=participant_updates,
            objective_updates=objective_updates,
            state_updates=state_updates,
            derived_events=derived_events,
            journal_payload=journal_payload,
            trace=trace,
        )

    def _resolve_stealth(
        self,
        state: EncounterState,
        action_meta: dict[str, Any],
        scene_summary: dict[str, Any],
        tick: int | None,
    ) -> EncounterResolution:
        action_type = action_meta.get("encounter_action_type", "stay_hidden")
        state_updates: dict[str, Any] = {"advance_turn": True}
        objective_updates: list[dict[str, Any]] = []
        outcome_type = "continue"
        derived_events: list[dict[str, Any]] = []

        if action_type in ("move_quietly", "slip_through"):
            for obj in state.objectives:
                if obj.kind in ("escape", "investigate") and obj.status == "active":
                    new_progress = min(obj.progress + 1, obj.required)
                    update: dict[str, Any] = {
                        "objective_id": obj.objective_id,
                        "progress": new_progress,
                    }
                    if new_progress >= obj.required:
                        update["status"] = "completed"
                        outcome_type = "resolve"
                    objective_updates.append(update)
                    break
            state_updates["mode_state"] = {"alert_level": "unaware"}

        elif action_type == "distract":
            state_updates["mode_state"] = {"alert_level": "distracted"}

        elif action_type == "observe_patrol":
            state_updates["mode_state"] = {"alert_level": "watching"}

        elif action_type == "retreat":
            outcome_type = "resolve"

        journal_payload = self._build_journal_payload(state, action_type, outcome_type, tick)
        trace = self._build_trace(state, action_type, outcome_type, "stealth")

        return EncounterResolution(
            encounter_id=state.encounter_id,
            mode="stealth",
            outcome_type=outcome_type,
            objective_updates=objective_updates,
            state_updates=state_updates,
            derived_events=derived_events,
            journal_payload=journal_payload,
            trace=trace,
        )

    def _resolve_investigation(
        self,
        state: EncounterState,
        action_meta: dict[str, Any],
        scene_summary: dict[str, Any],
        tick: int | None,
    ) -> EncounterResolution:
        action_type = action_meta.get("encounter_action_type", "inspect_area")
        state_updates: dict[str, Any] = {"advance_turn": True}
        objective_updates: list[dict[str, Any]] = []
        outcome_type = "continue"

        if action_type in ("inspect_area", "follow_lead", "compare_clues", "secure_evidence"):
            for obj in state.objectives:
                if obj.kind == "investigate" and obj.status == "active":
                    new_progress = min(obj.progress + 1, obj.required)
                    update: dict[str, Any] = {
                        "objective_id": obj.objective_id,
                        "progress": new_progress,
                    }
                    if new_progress >= obj.required:
                        update["status"] = "completed"
                        outcome_type = "resolve"
                    objective_updates.append(update)
                    break
            state_updates["mode_state"] = {"clue_progress": {"last_action": action_type}}

        elif action_type == "question_witness":
            state_updates["mode_state"] = {"lead_targets": [action_meta.get("target_id", "unknown")]}

        elif action_type == "test_theory":
            state_updates["mode_state"] = {"clue_progress": {"theory_tested": True}}

        journal_payload = self._build_journal_payload(state, action_type, outcome_type, tick)
        trace = self._build_trace(state, action_type, outcome_type, "investigation")

        return EncounterResolution(
            encounter_id=state.encounter_id,
            mode="investigation",
            outcome_type=outcome_type,
            objective_updates=objective_updates,
            state_updates=state_updates,
            journal_payload=journal_payload,
            trace=trace,
        )

    def _resolve_diplomacy(
        self,
        state: EncounterState,
        action_meta: dict[str, Any],
        scene_summary: dict[str, Any],
        tick: int | None,
    ) -> EncounterResolution:
        action_type = action_meta.get("encounter_action_type", "make_offer")
        state_updates: dict[str, Any] = {"advance_turn": True}
        objective_updates: list[dict[str, Any]] = []
        outcome_type = "continue"

        if action_type in ("make_offer", "reassure", "reveal_leverage"):
            for obj in state.objectives:
                if obj.kind == "convince" and obj.status == "active":
                    new_progress = min(obj.progress + 1, obj.required)
                    update: dict[str, Any] = {
                        "objective_id": obj.objective_id,
                        "progress": new_progress,
                    }
                    if new_progress >= obj.required:
                        update["status"] = "completed"
                        outcome_type = "resolve"
                    objective_updates.append(update)
                    break
            state_updates["mode_state"] = {"patience": "stable", "hostility_shift": "softening"}

        elif action_type == "threaten":
            state_updates["mode_state"] = {"hostility_shift": "hardening"}
            state_updates["pressure"] = "rising"

        elif action_type == "stall":
            state_updates["mode_state"] = {"patience": "thinning"}

        elif action_type == "concede_point":
            state_updates["mode_state"] = {"concession_count": 1}

        journal_payload = self._build_journal_payload(state, action_type, outcome_type, tick)
        trace = self._build_trace(state, action_type, outcome_type, "diplomacy")

        return EncounterResolution(
            encounter_id=state.encounter_id,
            mode="diplomacy",
            outcome_type=outcome_type,
            objective_updates=objective_updates,
            state_updates=state_updates,
            journal_payload=journal_payload,
            trace=trace,
        )

    def _resolve_chase(
        self,
        state: EncounterState,
        action_meta: dict[str, Any],
        scene_summary: dict[str, Any],
        tick: int | None,
    ) -> EncounterResolution:
        action_type = action_meta.get("encounter_action_type", "sprint")
        state_updates: dict[str, Any] = {"advance_turn": True}
        objective_updates: list[dict[str, Any]] = []
        outcome_type = "continue"

        if action_type in ("sprint", "maintain_pursuit"):
            for obj in state.objectives:
                if obj.kind in ("escape", "capture") and obj.status == "active":
                    new_progress = min(obj.progress + 1, obj.required)
                    update: dict[str, Any] = {
                        "objective_id": obj.objective_id,
                        "progress": new_progress,
                    }
                    if new_progress >= obj.required:
                        update["status"] = "completed"
                        outcome_type = "resolve"
                    objective_updates.append(update)
                    break
            state_updates["mode_state"] = {"fatigue": "tiring"}

        elif action_type == "evade_obstacle":
            state_updates["mode_state"] = {"distance_band": "widening"}

        elif action_type == "cut_off_route":
            state_updates["mode_state"] = {"distance_band": "closing"}

        elif action_type == "hide":
            outcome_type = "resolve"

        elif action_type == "force_confrontation":
            outcome_type = "escalate"
            state_updates["mode_state"] = {"distance_band": "close"}

        journal_payload = self._build_journal_payload(state, action_type, outcome_type, tick)
        trace = self._build_trace(state, action_type, outcome_type, "chase")

        return EncounterResolution(
            encounter_id=state.encounter_id,
            mode="chase",
            outcome_type=outcome_type,
            objective_updates=objective_updates,
            state_updates=state_updates,
            journal_payload=journal_payload,
            trace=trace,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_action_meta(resolved_action: Any) -> dict[str, Any]:
        """Pull encounter-relevant metadata from a resolved action."""
        if isinstance(resolved_action, dict):
            meta = dict(resolved_action.get("metadata", {}))
            meta.setdefault("encounter_action_type", resolved_action.get("intent_type", ""))
            meta.setdefault("target_id", resolved_action.get("target_id"))
            meta.setdefault("intent_type", resolved_action.get("intent_type", ""))
            return meta
        # Object with attributes
        meta = dict(getattr(resolved_action, "metadata", {}))
        meta.setdefault("encounter_action_type", getattr(resolved_action, "intent_type", ""))
        meta.setdefault("target_id", getattr(resolved_action, "target_id", None))
        meta.setdefault("intent_type", getattr(resolved_action, "intent_type", ""))
        return meta

    @staticmethod
    def _build_journal_payload(
        state: EncounterState,
        action_type: str,
        outcome_type: str,
        mode: str,
    ) -> dict[str, Any]:
        """Build a journal-safe payload for meaningful encounter events."""
        if outcome_type in ("resolve", "abort"):
            return {
                "encounter_id": state.encounter_id,
                "mode": mode,
                "action": action_type,
                "outcome_type": outcome_type,
                "journalable": True,
                "kind": f"encounter_{outcome_type}d" if outcome_type != "abort" else "encounter_aborted",
            }
        return {}

    @staticmethod
    def _build_trace(
        state: EncounterState,
        action_type: str,
        outcome_type: str,
        mode: str,
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "action_type": action_type,
            "outcome_type": outcome_type,
            "encounter_id": state.encounter_id,
            "round_index": state.round_index,
            "turn_index": state.turn_index,
            "reason": f"{action_type} in {mode} mode -> {outcome_type}",
        }
