"""Phase 8.2 — Encounter Controller.

Authoritative owner of current encounter state.  Explicit, serializable,
deterministic.  Manages the encounter lifecycle: start, apply resolution,
end, and choice-context building.

This controller may only mutate encounter state — never coherence, social,
or memory state directly.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .models import (
    SUPPORTED_ENCOUNTER_MODES,
    SUPPORTED_ENCOUNTER_STATUSES,
    EncounterChoiceContext,
    EncounterObjective,
    EncounterParticipant,
    EncounterResolution,
    EncounterState,
)


# ------------------------------------------------------------------
# Mode-specific default action sets
# ------------------------------------------------------------------

_MODE_ACTIONS: dict[str, list[str]] = {
    "combat": [
        "strike", "defend", "reposition", "use_cover",
        "press_advantage", "withdraw",
    ],
    "stealth": [
        "stay_hidden", "move_quietly", "distract", "observe_patrol",
        "slip_through", "retreat",
    ],
    "investigation": [
        "inspect_area", "question_witness", "compare_clues",
        "follow_lead", "test_theory", "secure_evidence",
    ],
    "diplomacy": [
        "make_offer", "threaten", "reassure", "reveal_leverage",
        "stall", "concede_point",
    ],
    "chase": [
        "sprint", "evade_obstacle", "cut_off_route", "hide",
        "force_confrontation", "maintain_pursuit",
    ],
}

# ------------------------------------------------------------------
# Mode-specific default mode_state templates
# ------------------------------------------------------------------

_MODE_STATE_DEFAULTS: dict[str, dict[str, Any]] = {
    "combat": {
        "engagements": [],
        "cover_map": {},
        "hazards": [],
        "momentum": "neutral",
    },
    "stealth": {
        "alert_level": "unaware",
        "suspicion_by_entity": {},
        "exposed_entities": [],
        "secure_routes": [],
    },
    "investigation": {
        "clue_progress": {},
        "searched_areas": [],
        "lead_targets": [],
        "false_leads": [],
    },
    "diplomacy": {
        "patience": "stable",
        "leverage": 0,
        "concession_count": 0,
        "hostility_shift": "neutral",
    },
    "chase": {
        "distance_band": "medium",
        "obstacles_remaining": 0,
        "route_control": "contested",
        "fatigue": "fresh",
    },
}


class EncounterController:
    """Authoritative owner of encounter state.

    Ownership boundary:
    - MAY mutate: active EncounterState and its nested encounter-owned models
    - MUST NOT mutate: coherence state, social state, memory state, arc state,
      filesystem state, external provider state, or any other truth owner
    """

    def __init__(self) -> None:
        self.active_encounter: EncounterState | None = None

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    def get_active_encounter(self) -> EncounterState | None:
        """Return the current encounter state (read-only accessor)."""
        return self.active_encounter

    def has_active_encounter(self) -> bool:
        """Return True if an encounter is currently active."""
        return (
            self.active_encounter is not None
            and self.active_encounter.status == "active"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_encounter(
        self,
        mode: str,
        scene_summary: dict[str, Any],
        participants: list[dict[str, Any]],
        objectives: list[dict[str, Any]] | None = None,
        stakes: str = "standard",
        active_entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tick: int | None = None,
    ) -> EncounterState:
        """Start a new encounter and set it as the active encounter.

        The encounter id is derived deterministically from tick, location,
        mode, and stable participant ordering.
        """
        mode = self._normalize_mode(mode)
        norm_participants = self._normalize_participants(participants)
        norm_objectives = self._normalize_objectives(objectives or [])

        location = scene_summary.get("location") or ""
        encounter_id = self._build_encounter_id(
            tick=tick, location=location, mode=mode, participants=norm_participants,
        )

        initiative = self._build_initiative(norm_participants)
        first_entity = active_entity_id or (initiative[0] if initiative else None)

        state = EncounterState(
            encounter_id=encounter_id,
            mode=mode,
            status="active",
            round_index=0,
            turn_index=0,
            scene_location=location or None,
            participants=norm_participants,
            objectives=norm_objectives,
            active_entity_id=first_entity,
            pressure="low",
            stakes=stakes,
            initiative=initiative,
            mode_state=self._build_default_mode_state(mode, norm_participants, scene_summary),
            metadata=dict(metadata) if metadata else {},
        )

        self.active_encounter = state
        return state

    def end_encounter(
        self,
        status: str = "resolved",
        resolution_summary: dict[str, Any] | None = None,
    ) -> None:
        """Mark the encounter as finished.

        The resolved state is retained until the next explicit start or
        clear so that UX and memory layers can still read it.
        """
        if self.active_encounter is None:
            return
        if status not in SUPPORTED_ENCOUNTER_STATUSES:
            status = "resolved"
        self.active_encounter.status = status
        if resolution_summary:
            self.active_encounter.resolution_summary = dict(resolution_summary)

    def clear_encounter(self) -> None:
        """Explicitly discard the encounter state."""
        self.active_encounter = None

    # ------------------------------------------------------------------
    # Choice context for gameplay control
    # ------------------------------------------------------------------

    def build_choice_context(
        self,
        player_id: str = "player",
        coherence_core: Any = None,
    ) -> EncounterChoiceContext | None:
        """Build encounter-facing constraints for gameplay control.

        Returns ``None`` when no active encounter exists.
        """
        if not self.has_active_encounter():
            return None

        state = self.active_encounter
        assert state is not None  # guarded by has_active_encounter

        player_participant = next(
            (p for p in state.participants if p.entity_id == player_id),
            None,
        )
        player_role = player_participant.role if player_participant else "player"

        available_actions = list(_MODE_ACTIONS.get(state.mode, []))

        # Build objective pressure summary
        objective_pressure: dict[str, Any] = {}
        for obj in state.objectives:
            if obj.status == "active":
                objective_pressure[obj.objective_id] = {
                    "kind": obj.kind,
                    "progress": obj.progress,
                    "required": obj.required,
                }

        return EncounterChoiceContext(
            encounter_id=state.encounter_id,
            mode=state.mode,
            status=state.status,
            active_entity_id=state.active_entity_id,
            player_role=player_role,
            available_actions=available_actions,
            constraints={"pressure": state.pressure, "stakes": state.stakes},
            objective_pressure=objective_pressure,
            mode_state=dict(state.mode_state),
        )

    # ------------------------------------------------------------------
    # Resolution application
    # ------------------------------------------------------------------

    def apply_resolution(
        self, resolution: EncounterResolution
    ) -> EncounterState | None:
        """Apply an encounter resolution to the active encounter state.

        This method mutates ONLY encounter-owned state.
        It must never mutate coherence, social state, memory, or any other
        authoritative subsystem.
        """
        state = self.active_encounter
        if state is None:
            return None
        if resolution is None:
            return state
        if resolution.encounter_id and resolution.encounter_id != state.encounter_id:
            return state

        # participant updates — whitelist encounter-owned fields only
        allowed_participant_fields = {"role", "team", "status", "position", "tags", "metadata"}
        by_id = {p.entity_id: p for p in state.participants}
        for update in resolution.participant_updates:
            if not isinstance(update, dict):
                continue
            entity_id = update.get("entity_id")
            if not entity_id or entity_id not in by_id:
                continue
            participant = by_id[entity_id]
            for key, value in update.items():
                if key == "entity_id" or key not in allowed_participant_fields:
                    continue
                if key == "tags":
                    participant.tags = list(value) if isinstance(value, list) else []
                elif key == "metadata":
                    participant.metadata = dict(value) if isinstance(value, dict) else {}
                else:
                    setattr(participant, key, value)

        # objective updates — whitelist encounter-owned fields only
        allowed_objective_fields = {"kind", "owner_id", "target_id", "status", "progress", "required", "metadata"}
        objectives_by_id = {o.objective_id: o for o in state.objectives}
        for update in resolution.objective_updates:
            if not isinstance(update, dict):
                continue
            objective_id = update.get("objective_id")
            if not objective_id or objective_id not in objectives_by_id:
                continue
            objective = objectives_by_id[objective_id]
            for key, value in update.items():
                if key == "objective_id" or key not in allowed_objective_fields:
                    continue
                if key == "metadata":
                    objective.metadata = dict(value) if isinstance(value, dict) else {}
                else:
                    setattr(objective, key, value)

        # encounter-state updates — whitelist only encounter-owned fields
        allowed_state_fields = {
            "status",
            "round_index",
            "turn_index",
            "active_entity_id",
            "pressure",
            "stakes",
            "visibility",
            "initiative",
            "mode_state",
            "resolution_summary",
            "metadata",
        }
        for key, value in (resolution.state_updates or {}).items():
            if key not in allowed_state_fields:
                continue
            if key in {"visibility", "mode_state", "resolution_summary", "metadata"}:
                setattr(state, key, dict(value) if isinstance(value, dict) else {})
            elif key == "initiative":
                setattr(state, key, list(value) if isinstance(value, list) else [])
            else:
                setattr(state, key, value)

        # advance turn order only if the resolution did not already set it explicitly
        explicit_turn_control = any(
            key in (resolution.state_updates or {})
            for key in ("turn_index", "round_index", "active_entity_id", "initiative", "advance_turn")
        )
        if not explicit_turn_control and state.status == "active":
            self._advance_turn_order(state)
        elif (resolution.state_updates or {}).get("advance_turn"):
            self._advance_turn_order(state)

        # auto-resolve if all objectives complete/failed
        if state.objectives:
            all_terminal = all(
                objective.status in {"completed", "failed", "blocked"}
                for objective in state.objectives
            )
            if all_terminal and state.status == "active":
                state.status = "resolved"

        self.active_encounter = state
        return state

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "active_encounter": self.active_encounter.to_dict() if self.active_encounter else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterController":
        ctrl = cls()
        ae = data.get("active_encounter")
        ctrl.active_encounter = EncounterState.from_dict(ae) if ae else None
        return ctrl

    # ------------------------------------------------------------------
    # Phase 8.3 — World simulation seed (read-only)
    # ------------------------------------------------------------------

    def build_world_sim_seed(self) -> dict:
        """Return read-only encounter aftermath data for world sim seeding.

        Exposes recent encounter mode/status and summary without mutating
        encounter state.
        """
        state = self.active_encounter
        if state is None:
            return {}

        return {
            "mode": state.mode,
            "status": state.status,
            "location": state.metadata.get("location", ""),
            "pressure": state.pressure,
            "stakes": state.stakes,
            "participant_count": len(state.participants),
            "resolved": state.status in ("resolved", "finished"),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        mode = mode.strip().lower()
        if mode not in SUPPORTED_ENCOUNTER_MODES:
            mode = "combat"
        return mode

    @staticmethod
    def _normalize_participants(
        raw: list[dict[str, Any]],
    ) -> list[EncounterParticipant]:
        participants: list[EncounterParticipant] = []
        for entry in raw:
            participants.append(EncounterParticipant.from_dict(entry))
        # Stable sort for determinism
        participants.sort(key=lambda p: p.entity_id)
        return participants

    @staticmethod
    def _normalize_objectives(
        raw: list[dict[str, Any]],
    ) -> list[EncounterObjective]:
        objectives: list[EncounterObjective] = []
        for entry in raw:
            objectives.append(EncounterObjective.from_dict(entry))
        objectives.sort(key=lambda o: o.objective_id)
        return objectives

    @staticmethod
    def _build_encounter_id(
        tick: int | None,
        location: str,
        mode: str,
        participants: list[EncounterParticipant],
    ) -> str:
        """Derive a deterministic encounter id."""
        parts = [
            str(tick) if tick is not None else "0",
            location,
            mode,
            ",".join(p.entity_id for p in participants),
        ]
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
        return f"enc:{mode}:{digest}"

    @staticmethod
    def _build_initiative(
        participants: list[EncounterParticipant],
    ) -> list[str]:
        """Build deterministic initiative order.

        Priority: player > ally > neutral > enemy > bystander > target.
        Within same role, sorted by entity_id.
        """
        role_priority = {
            "player": 0, "ally": 1, "neutral": 2,
            "enemy": 3, "bystander": 4, "target": 5,
        }
        ordered = sorted(
            participants,
            key=lambda p: (role_priority.get(p.role, 99), p.entity_id),
        )
        return [p.entity_id for p in ordered]

    @staticmethod
    def _build_default_mode_state(
        mode: str,
        participants: list[EncounterParticipant],
        scene_summary: dict[str, Any],
    ) -> dict[str, Any]:
        defaults = dict(_MODE_STATE_DEFAULTS.get(mode, {}))
        # Deep-copy nested mutable structures
        for key, val in defaults.items():
            if isinstance(val, list):
                defaults[key] = list(val)
            elif isinstance(val, dict):
                defaults[key] = dict(val)
        return defaults

    @staticmethod
    def _advance_turn_order(state: EncounterState) -> None:
        """Advance to the next entity in initiative order."""
        if not state.initiative:
            return
        state.turn_index += 1
        if state.turn_index >= len(state.initiative):
            state.turn_index = 0
            state.round_index += 1
        state.active_entity_id = state.initiative[state.turn_index]

    @staticmethod
    def _compute_pressure(state: EncounterState) -> str:
        """Derive pressure label from encounter state."""
        active_enemies = sum(
            1 for p in state.participants
            if p.role == "enemy" and p.status == "active"
        )
        active_objectives = sum(
            1 for o in state.objectives
            if o.status == "active"
        )
        if active_enemies == 0 and active_objectives == 0:
            return "low"
        if active_enemies >= 3 or active_objectives >= 3:
            return "critical"
        if active_enemies >= 2 or active_objectives >= 2:
            return "high"
        return "rising"
