"""Phase 8.2 — Encounter Unit Tests.

Covers pure logic: models roundtrip, controller lifecycle, resolver
determinism, presenter output, journal builder, and memory core recording.
"""

from __future__ import annotations

import copy
import os
import sys

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.encounter.models import (
    SUPPORTED_ENCOUNTER_MODES,
    SUPPORTED_ENCOUNTER_STATUSES,
    EncounterChoiceContext,
    EncounterObjective,
    EncounterParticipant,
    EncounterResolution,
    EncounterSnapshot,
    EncounterState,
)
from app.rpg.encounter.controller import EncounterController
from app.rpg.encounter.resolver import EncounterResolver
from app.rpg.encounter.presenter import EncounterPresenter
from app.rpg.memory.journal_builder import JournalBuilder
from app.rpg.memory.core import CampaignMemoryCore


# ======================================================================
# Helpers — shared fixture builders
# ======================================================================

def _make_participant(entity_id: str = "player", role: str = "player", **kw) -> dict:
    return {"entity_id": entity_id, "role": role, **kw}


def _make_objective(
    objective_id: str = "obj-1",
    kind: str = "defeat",
    progress: int = 0,
    required: int = 3,
    **kw,
) -> dict:
    return {
        "objective_id": objective_id,
        "kind": kind,
        "progress": progress,
        "required": required,
        **kw,
    }


def _scene_summary(location: str = "dark_alley") -> dict:
    return {"location": location, "description": "A dark alley."}


def _start_combat_encounter(
    ctrl: EncounterController | None = None,
    tick: int = 1,
    participants: list[dict] | None = None,
    objectives: list[dict] | None = None,
    mode: str = "combat",
) -> tuple[EncounterController, EncounterState]:
    ctrl = ctrl or EncounterController()
    participants = participants or [
        _make_participant("player", "player"),
        _make_participant("goblin_a", "enemy"),
        _make_participant("ally_npc", "ally"),
    ]
    objectives = objectives or [_make_objective("obj-1", "defeat", 0, 3)]
    state = ctrl.start_encounter(
        mode=mode,
        scene_summary=_scene_summary(),
        participants=participants,
        objectives=objectives,
        tick=tick,
    )
    return ctrl, state


# ======================================================================
# Model tests
# ======================================================================

class TestSupportedConstants:
    """Verify encounter constants contain expected values."""

    def test_supported_modes_contains_combat(self):
        assert "combat" in SUPPORTED_ENCOUNTER_MODES

    def test_supported_modes_contains_stealth(self):
        assert "stealth" in SUPPORTED_ENCOUNTER_MODES

    def test_supported_modes_contains_investigation(self):
        assert "investigation" in SUPPORTED_ENCOUNTER_MODES

    def test_supported_modes_contains_diplomacy(self):
        assert "diplomacy" in SUPPORTED_ENCOUNTER_MODES

    def test_supported_modes_contains_chase(self):
        assert "chase" in SUPPORTED_ENCOUNTER_MODES

    def test_supported_modes_count(self):
        assert len(SUPPORTED_ENCOUNTER_MODES) == 5

    def test_supported_statuses_contains_expected(self):
        expected = {"inactive", "active", "resolved", "aborted"}
        assert SUPPORTED_ENCOUNTER_STATUSES == expected


class TestEncounterParticipantModel:
    """EncounterParticipant dataclass tests."""

    def test_defaults(self):
        p = EncounterParticipant(entity_id="npc1", role="enemy")
        assert p.status == "active"
        assert p.team is None
        assert p.position is None
        assert p.tags == []
        assert p.metadata == {}

    def test_to_dict_from_dict_roundtrip(self):
        p = EncounterParticipant(
            entity_id="hero",
            role="player",
            team="party",
            status="engaged",
            position="front",
            tags=["leader"],
            metadata={"hp": 100},
        )
        d = p.to_dict()
        restored = EncounterParticipant.from_dict(d)
        assert restored.entity_id == p.entity_id
        assert restored.role == p.role
        assert restored.team == p.team
        assert restored.status == p.status
        assert restored.position == p.position
        assert restored.tags == p.tags
        assert restored.metadata == p.metadata

    def test_from_dict_missing_fields_get_defaults(self):
        p = EncounterParticipant.from_dict({})
        assert p.entity_id == ""
        assert p.role == "neutral"
        assert p.status == "active"

    def test_to_dict_returns_copies(self):
        p = EncounterParticipant(entity_id="a", role="enemy", tags=["t1"])
        d = p.to_dict()
        d["tags"].append("mutated")
        assert "mutated" not in p.tags


class TestEncounterObjectiveModel:
    """EncounterObjective dataclass tests."""

    def test_defaults(self):
        o = EncounterObjective(objective_id="o1", kind="defeat")
        assert o.status == "active"
        assert o.progress == 0
        assert o.required == 1
        assert o.owner_id is None
        assert o.target_id is None

    def test_to_dict_from_dict_roundtrip(self):
        o = EncounterObjective(
            objective_id="o2",
            kind="escape",
            owner_id="player",
            target_id="exit",
            status="progressed",
            progress=2,
            required=5,
            metadata={"notes": "hurry"},
        )
        d = o.to_dict()
        restored = EncounterObjective.from_dict(d)
        assert restored.objective_id == o.objective_id
        assert restored.kind == o.kind
        assert restored.progress == o.progress
        assert restored.required == o.required
        assert restored.metadata == o.metadata

    def test_from_dict_missing_fields_get_defaults(self):
        o = EncounterObjective.from_dict({})
        assert o.objective_id == ""
        assert o.kind == ""
        assert o.status == "active"
        assert o.progress == 0
        assert o.required == 1


class TestEncounterStateModel:
    """EncounterState dataclass tests."""

    def test_defaults(self):
        s = EncounterState(encounter_id="e1", mode="combat")
        assert s.status == "active"
        assert s.round_index == 0
        assert s.turn_index == 0
        assert s.participants == []
        assert s.objectives == []
        assert s.pressure == "low"
        assert s.stakes == "standard"

    def test_to_dict_from_dict_roundtrip(self):
        s = EncounterState(
            encounter_id="e2",
            mode="stealth",
            status="active",
            round_index=3,
            turn_index=1,
            scene_location="forest",
            participants=[EncounterParticipant(entity_id="p1", role="player")],
            objectives=[EncounterObjective(objective_id="o1", kind="escape")],
            active_entity_id="p1",
            pressure="high",
            stakes="high",
            initiative=["p1"],
            mode_state={"alert_level": "unaware"},
            metadata={"started_by": "gm"},
        )
        d = s.to_dict()
        restored = EncounterState.from_dict(d)
        assert restored.encounter_id == s.encounter_id
        assert restored.mode == s.mode
        assert restored.round_index == s.round_index
        assert restored.turn_index == s.turn_index
        assert restored.scene_location == s.scene_location
        assert len(restored.participants) == 1
        assert restored.participants[0].entity_id == "p1"
        assert len(restored.objectives) == 1
        assert restored.objectives[0].objective_id == "o1"
        assert restored.pressure == "high"
        assert restored.initiative == ["p1"]
        assert restored.mode_state == {"alert_level": "unaware"}

    def test_from_dict_empty_data(self):
        s = EncounterState.from_dict({})
        assert s.encounter_id == ""
        assert s.mode == "combat"
        assert s.status == "active"


class TestEncounterChoiceContextModel:
    """EncounterChoiceContext dataclass tests."""

    def test_defaults(self):
        c = EncounterChoiceContext()
        assert c.encounter_id is None
        assert c.mode is None
        assert c.player_role == "player"
        assert c.available_actions == []

    def test_to_dict_from_dict_roundtrip(self):
        c = EncounterChoiceContext(
            encounter_id="e1",
            mode="combat",
            status="active",
            active_entity_id="player",
            available_actions=["strike", "defend"],
            constraints={"pressure": "high"},
            mode_state={"momentum": "neutral"},
        )
        d = c.to_dict()
        restored = EncounterChoiceContext.from_dict(d)
        assert restored.encounter_id == c.encounter_id
        assert restored.available_actions == c.available_actions
        assert restored.constraints == c.constraints


class TestEncounterResolutionModel:
    """EncounterResolution dataclass tests."""

    def test_defaults(self):
        r = EncounterResolution()
        assert r.outcome_type == "continue"
        assert r.participant_updates == []
        assert r.objective_updates == []

    def test_to_dict_from_dict_roundtrip(self):
        r = EncounterResolution(
            encounter_id="e1",
            mode="combat",
            outcome_type="resolve",
            participant_updates=[{"entity_id": "g1", "status": "downed"}],
            objective_updates=[{"objective_id": "o1", "progress": 3}],
            state_updates={"pressure": "low"},
            journal_payload={"journalable": True, "kind": "encounter_resolved"},
            trace={"reason": "test"},
        )
        d = r.to_dict()
        restored = EncounterResolution.from_dict(d)
        assert restored.encounter_id == r.encounter_id
        assert restored.outcome_type == "resolve"
        assert restored.participant_updates == r.participant_updates
        assert restored.journal_payload == r.journal_payload


class TestEncounterSnapshotModel:
    """EncounterSnapshot dataclass tests."""

    def test_defaults(self):
        s = EncounterSnapshot()
        assert s.active_encounter is None

    def test_to_dict_from_dict_roundtrip_with_data(self):
        s = EncounterSnapshot(active_encounter={"encounter_id": "e1", "mode": "chase"})
        d = s.to_dict()
        restored = EncounterSnapshot.from_dict(d)
        assert restored.active_encounter == {"encounter_id": "e1", "mode": "chase"}

    def test_to_dict_from_dict_roundtrip_none(self):
        s = EncounterSnapshot()
        d = s.to_dict()
        restored = EncounterSnapshot.from_dict(d)
        assert restored.active_encounter is None


# ======================================================================
# Controller lifecycle tests
# ======================================================================

class TestControllerStartEncounter:
    """EncounterController.start_encounter tests."""

    def test_start_produces_active_state(self):
        ctrl, state = _start_combat_encounter()
        assert state.status == "active"
        assert ctrl.has_active_encounter() is True

    def test_start_sets_mode(self):
        _, state = _start_combat_encounter(mode="stealth")
        assert state.mode == "stealth"

    def test_start_normalizes_unknown_mode_to_combat(self):
        _, state = _start_combat_encounter(mode="UNKNOWN_MODE")
        assert state.mode == "combat"

    def test_start_normalizes_mode_case_insensitive(self):
        _, state = _start_combat_encounter(mode="STEALTH")
        assert state.mode == "stealth"

    def test_start_with_each_supported_mode(self):
        for mode in SUPPORTED_ENCOUNTER_MODES:
            _, state = _start_combat_encounter(mode=mode)
            assert state.mode == mode

    def test_participants_sorted_by_entity_id(self):
        participants = [
            _make_participant("zoe", "player"),
            _make_participant("alice", "ally"),
            _make_participant("mike", "enemy"),
        ]
        _, state = _start_combat_encounter(participants=participants)
        ids = [p.entity_id for p in state.participants]
        assert ids == sorted(ids)

    def test_objectives_sorted_by_objective_id(self):
        objectives = [
            _make_objective("z-obj"),
            _make_objective("a-obj"),
            _make_objective("m-obj"),
        ]
        _, state = _start_combat_encounter(objectives=objectives)
        oids = [o.objective_id for o in state.objectives]
        assert oids == sorted(oids)

    def test_encounter_id_is_deterministic(self):
        _, state1 = _start_combat_encounter(tick=42)
        _, state2 = _start_combat_encounter(tick=42)
        assert state1.encounter_id == state2.encounter_id

    def test_encounter_id_changes_with_tick(self):
        _, state1 = _start_combat_encounter(tick=1)
        _, state2 = _start_combat_encounter(tick=2)
        assert state1.encounter_id != state2.encounter_id

    def test_encounter_id_changes_with_mode(self):
        _, state1 = _start_combat_encounter(mode="combat", tick=1)
        _, state2 = _start_combat_encounter(mode="stealth", tick=1)
        assert state1.encounter_id != state2.encounter_id

    def test_encounter_id_prefix_contains_mode(self):
        _, state = _start_combat_encounter(mode="stealth", tick=1)
        assert state.encounter_id.startswith("enc:stealth:")

    def test_initiative_order_player_before_ally_before_enemy(self):
        participants = [
            _make_participant("enemy_1", "enemy"),
            _make_participant("ally_1", "ally"),
            _make_participant("player_1", "player"),
        ]
        _, state = _start_combat_encounter(participants=participants)
        init = state.initiative
        p_idx = init.index("player_1")
        a_idx = init.index("ally_1")
        e_idx = init.index("enemy_1")
        assert p_idx < a_idx < e_idx

    def test_initiative_includes_neutral_between_ally_and_enemy(self):
        participants = [
            _make_participant("enemy_1", "enemy"),
            _make_participant("neutral_1", "neutral"),
            _make_participant("player_1", "player"),
        ]
        _, state = _start_combat_encounter(participants=participants)
        init = state.initiative
        assert init.index("player_1") < init.index("neutral_1") < init.index("enemy_1")

    def test_active_entity_defaults_to_first_in_initiative(self):
        participants = [
            _make_participant("enemy_1", "enemy"),
            _make_participant("player_1", "player"),
        ]
        _, state = _start_combat_encounter(participants=participants)
        assert state.active_entity_id == "player_1"

    def test_active_entity_respects_explicit_override(self):
        ctrl = EncounterController()
        state = ctrl.start_encounter(
            mode="combat",
            scene_summary=_scene_summary(),
            participants=[_make_participant("p", "player"), _make_participant("e", "enemy")],
            active_entity_id="e",
            tick=1,
        )
        assert state.active_entity_id == "e"

    def test_default_mode_state_combat(self):
        _, state = _start_combat_encounter(mode="combat")
        assert "momentum" in state.mode_state

    def test_default_mode_state_stealth(self):
        _, state = _start_combat_encounter(mode="stealth")
        assert "alert_level" in state.mode_state

    def test_default_mode_state_investigation(self):
        _, state = _start_combat_encounter(mode="investigation")
        assert "clue_progress" in state.mode_state

    def test_default_mode_state_diplomacy(self):
        _, state = _start_combat_encounter(mode="diplomacy")
        assert "patience" in state.mode_state

    def test_default_mode_state_chase(self):
        _, state = _start_combat_encounter(mode="chase")
        assert "distance_band" in state.mode_state

    def test_scene_location_populated(self):
        _, state = _start_combat_encounter()
        assert state.scene_location == "dark_alley"

    def test_round_and_turn_start_at_zero(self):
        _, state = _start_combat_encounter()
        assert state.round_index == 0
        assert state.turn_index == 0


class TestControllerEndEncounter:
    """EncounterController.end_encounter tests."""

    def test_end_marks_resolved(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.end_encounter()
        assert ctrl.active_encounter is not None
        assert ctrl.active_encounter.status == "resolved"

    def test_end_retains_state(self):
        ctrl, state = _start_combat_encounter()
        ctrl.end_encounter()
        assert ctrl.active_encounter.encounter_id == state.encounter_id

    def test_end_with_custom_status(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.end_encounter(status="aborted")
        assert ctrl.active_encounter.status == "aborted"

    def test_end_with_invalid_status_defaults_to_resolved(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.end_encounter(status="bogus_status")
        assert ctrl.active_encounter.status == "resolved"

    def test_end_with_resolution_summary(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.end_encounter(resolution_summary={"winner": "player"})
        assert ctrl.active_encounter.resolution_summary == {"winner": "player"}

    def test_end_no_active_encounter_is_noop(self):
        ctrl = EncounterController()
        ctrl.end_encounter()  # should not raise

    def test_has_active_encounter_false_after_end(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.end_encounter()
        assert ctrl.has_active_encounter() is False


class TestControllerClearEncounter:
    """EncounterController.clear_encounter tests."""

    def test_clear_sets_none(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.clear_encounter()
        assert ctrl.active_encounter is None

    def test_has_active_encounter_false_after_clear(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.clear_encounter()
        assert ctrl.has_active_encounter() is False

    def test_get_active_encounter_none_after_clear(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.clear_encounter()
        assert ctrl.get_active_encounter() is None


class TestControllerBuildChoiceContext:
    """EncounterController.build_choice_context tests."""

    def test_returns_none_when_no_encounter(self):
        ctrl = EncounterController()
        assert ctrl.build_choice_context() is None

    def test_returns_none_after_end(self):
        ctrl, _ = _start_combat_encounter()
        ctrl.end_encounter()
        assert ctrl.build_choice_context() is None

    def test_returns_context_for_active_encounter(self):
        ctrl, _ = _start_combat_encounter()
        ctx = ctrl.build_choice_context(player_id="player")
        assert ctx is not None
        assert isinstance(ctx, EncounterChoiceContext)

    def test_context_has_correct_mode(self):
        ctrl, _ = _start_combat_encounter(mode="stealth")
        ctx = ctrl.build_choice_context()
        assert ctx.mode == "stealth"

    def test_combat_actions_present(self):
        ctrl, _ = _start_combat_encounter(mode="combat")
        ctx = ctrl.build_choice_context()
        assert "strike" in ctx.available_actions
        assert "defend" in ctx.available_actions

    def test_stealth_actions_present(self):
        ctrl, _ = _start_combat_encounter(mode="stealth")
        ctx = ctrl.build_choice_context()
        assert "stay_hidden" in ctx.available_actions
        assert "move_quietly" in ctx.available_actions

    def test_investigation_actions_present(self):
        ctrl, _ = _start_combat_encounter(mode="investigation")
        ctx = ctrl.build_choice_context()
        assert "inspect_area" in ctx.available_actions

    def test_diplomacy_actions_present(self):
        ctrl, _ = _start_combat_encounter(mode="diplomacy")
        ctx = ctrl.build_choice_context()
        assert "make_offer" in ctx.available_actions

    def test_chase_actions_present(self):
        ctrl, _ = _start_combat_encounter(mode="chase")
        ctx = ctrl.build_choice_context()
        assert "sprint" in ctx.available_actions

    def test_context_includes_objective_pressure(self):
        ctrl, _ = _start_combat_encounter()
        ctx = ctrl.build_choice_context()
        assert "obj-1" in ctx.objective_pressure

    def test_context_player_role(self):
        ctrl, _ = _start_combat_encounter()
        ctx = ctrl.build_choice_context(player_id="player")
        assert ctx.player_role == "player"

    def test_context_constraints_include_pressure_and_stakes(self):
        ctrl, _ = _start_combat_encounter()
        ctx = ctrl.build_choice_context()
        assert "pressure" in ctx.constraints
        assert "stakes" in ctx.constraints


class TestControllerApplyResolution:
    """EncounterController.apply_resolution tests."""

    def test_returns_none_when_no_encounter(self):
        ctrl = EncounterController()
        res = EncounterResolution(outcome_type="continue")
        assert ctrl.apply_resolution(res) is None

    def test_updates_participant_status(self):
        ctrl, state = _start_combat_encounter()
        target_id = state.participants[-1].entity_id
        res = EncounterResolution(
            participant_updates=[{"entity_id": target_id, "status": "downed"}],
        )
        ctrl.apply_resolution(res)
        updated = next(p for p in state.participants if p.entity_id == target_id)
        assert updated.status == "downed"

    def test_updates_participant_tags(self):
        ctrl, state = _start_combat_encounter()
        target_id = state.participants[0].entity_id
        res = EncounterResolution(
            participant_updates=[{"entity_id": target_id, "tags": ["stunned"]}],
        )
        ctrl.apply_resolution(res)
        updated = next(p for p in state.participants if p.entity_id == target_id)
        assert "stunned" in updated.tags

    def test_updates_participant_position(self):
        ctrl, state = _start_combat_encounter()
        target_id = state.participants[0].entity_id
        res = EncounterResolution(
            participant_updates=[{"entity_id": target_id, "position": "flank"}],
        )
        ctrl.apply_resolution(res)
        updated = next(p for p in state.participants if p.entity_id == target_id)
        assert updated.position == "flank"

    def test_updates_objective_progress(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(
            objective_updates=[{"objective_id": "obj-1", "progress": 2}],
        )
        ctrl.apply_resolution(res)
        obj = state.objectives[0]
        assert obj.progress == 2

    def test_updates_objective_status(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(
            objective_updates=[{"objective_id": "obj-1", "status": "completed"}],
        )
        ctrl.apply_resolution(res)
        assert state.objectives[0].status == "completed"

    def test_advance_turn(self):
        ctrl, state = _start_combat_encounter()
        first_entity = state.active_entity_id
        res = EncounterResolution(
            state_updates={"advance_turn": True},
        )
        ctrl.apply_resolution(res)
        assert state.turn_index == 1
        assert state.active_entity_id != first_entity or len(state.initiative) == 1

    def test_advance_turn_wraps_round(self):
        ctrl, state = _start_combat_encounter()
        n = len(state.initiative)
        for _ in range(n):
            res = EncounterResolution(state_updates={"advance_turn": True})
            ctrl.apply_resolution(res)
        assert state.round_index == 1
        assert state.turn_index == 0

    def test_resolve_outcome_sets_resolved(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(outcome_type="resolve")
        ctrl.apply_resolution(res)
        assert state.status == "resolved"

    def test_abort_outcome_sets_aborted(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(outcome_type="abort")
        ctrl.apply_resolution(res)
        assert state.status == "aborted"

    def test_continue_outcome_keeps_active(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(outcome_type="continue")
        ctrl.apply_resolution(res)
        assert state.status == "active"

    def test_updates_pressure(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(state_updates={"pressure": "critical"})
        ctrl.apply_resolution(res)
        assert state.pressure == "critical"

    def test_updates_mode_state(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(state_updates={"mode_state": {"momentum": "attacking"}})
        ctrl.apply_resolution(res)
        assert state.mode_state["momentum"] == "attacking"

    def test_ignores_unknown_participant(self):
        ctrl, state = _start_combat_encounter()
        res = EncounterResolution(
            participant_updates=[{"entity_id": "nonexistent", "status": "downed"}],
        )
        ctrl.apply_resolution(res)  # should not raise


class TestControllerSerialization:
    """EncounterController to_dict/from_dict tests."""

    def test_roundtrip_with_active_encounter(self):
        ctrl, _ = _start_combat_encounter()
        d = ctrl.to_dict()
        restored = EncounterController.from_dict(d)
        assert restored.active_encounter is not None
        assert restored.active_encounter.encounter_id == ctrl.active_encounter.encounter_id
        assert restored.active_encounter.mode == ctrl.active_encounter.mode

    def test_roundtrip_without_encounter(self):
        ctrl = EncounterController()
        d = ctrl.to_dict()
        restored = EncounterController.from_dict(d)
        assert restored.active_encounter is None

    def test_roundtrip_preserves_participants(self):
        ctrl, state = _start_combat_encounter()
        d = ctrl.to_dict()
        restored = EncounterController.from_dict(d)
        original_ids = [p.entity_id for p in state.participants]
        restored_ids = [p.entity_id for p in restored.active_encounter.participants]
        assert original_ids == restored_ids


# ======================================================================
# Resolver tests
# ======================================================================

class TestResolverResolveAction:
    """EncounterResolver.resolve_action tests."""

    def test_returns_none_for_no_encounter(self):
        resolver = EncounterResolver()
        result = resolver.resolve_action(None, {}, {})
        assert result is None

    def test_returns_none_for_resolved_encounter(self):
        resolver = EncounterResolver()
        state = EncounterState(encounter_id="e1", mode="combat", status="resolved")
        result = resolver.resolve_action(state, {}, {})
        assert result is None

    def test_returns_resolution_for_active_encounter(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"intent_type": "strike", "metadata": {"encounter_action_type": "strike"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result is not None
        assert isinstance(result, EncounterResolution)

    def test_determinism_same_action_same_state(self):
        resolver = EncounterResolver()
        _, state1 = _start_combat_encounter(tick=1)
        _, state2 = _start_combat_encounter(tick=1)
        action = {"intent_type": "strike", "metadata": {"encounter_action_type": "strike"}}
        r1 = resolver.resolve_action(state1, action, _scene_summary())
        r2 = resolver.resolve_action(state2, action, _scene_summary())
        assert r1.to_dict() == r2.to_dict()


class TestResolverDetectEncounterStart:
    """EncounterResolver.detect_encounter_start tests."""

    def test_explicit_metadata(self):
        result = EncounterResolver.detect_encounter_start({"encounter_start": "combat"})
        assert result == "combat"

    def test_explicit_stealth(self):
        result = EncounterResolver.detect_encounter_start({"encounter_start": "stealth"})
        assert result == "stealth"

    def test_explicit_invalid_mode_returns_none(self):
        result = EncounterResolver.detect_encounter_start({"encounter_start": "bogus"})
        assert result is None

    def test_tag_attack_detects_combat(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["attack"]})
        assert result == "combat"

    def test_tag_sneak_detects_stealth(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["sneak"]})
        assert result == "stealth"

    def test_tag_investigate_detects_investigation(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["investigate"]})
        assert result == "investigation"

    def test_tag_negotiate_detects_diplomacy(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["negotiate"]})
        assert result == "diplomacy"

    def test_tag_flee_detects_chase(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["flee"]})
        assert result == "chase"

    def test_tag_pursue_detects_chase(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["pursue"]})
        assert result == "chase"

    def test_encounter_tags_key(self):
        result = EncounterResolver.detect_encounter_start({"encounter_tags": ["ambush"]})
        assert result == "combat"

    def test_intent_type_detection(self):
        result = EncounterResolver.detect_encounter_start({"intent_type": "attack"})
        assert result == "combat"

    def test_intent_type_demand_detects_diplomacy(self):
        result = EncounterResolver.detect_encounter_start({"intent_type": "demand"})
        assert result == "diplomacy"

    def test_returns_none_for_non_encounter(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["talk", "walk"]})
        assert result is None

    def test_returns_none_for_empty_meta(self):
        result = EncounterResolver.detect_encounter_start({})
        assert result is None

    def test_tag_case_insensitive(self):
        result = EncounterResolver.detect_encounter_start({"tags": ["ATTACK"]})
        assert result == "combat"


class TestResolverCombatMode:
    """Combat-mode resolution tests."""

    def test_strike_engages_target(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        enemy_id = next(p.entity_id for p in state.participants if p.role == "enemy")
        action = {"metadata": {"encounter_action_type": "strike", "target_id": enemy_id}}
        result = resolver.resolve_action(state, action, _scene_summary())
        has_update = any(
            u["entity_id"] == enemy_id and u["status"] == "engaged"
            for u in result.participant_updates
        )
        assert has_update

    def test_strike_advances_defeat_objective(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "strike"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert any(u.get("progress", 0) > 0 for u in result.objective_updates)

    def test_defend_sets_defensive_momentum(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "defend"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("mode_state", {}).get("momentum") == "defensive"

    def test_withdraw_resolves_encounter(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "withdraw"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.outcome_type == "resolve"

    def test_reposition_continues(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "reposition"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.outcome_type == "continue"

    def test_objective_completion_resolves(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "defeat", progress=2, required=3)]
        _, state = _start_combat_encounter(objectives=objectives)
        action = {"metadata": {"encounter_action_type": "strike"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        has_completed = any(
            u.get("status") == "completed" for u in result.objective_updates
        )
        assert has_completed
        assert result.outcome_type == "resolve"


class TestResolverStealthMode:
    """Stealth-mode resolution tests."""

    def test_move_quietly_progresses_escape(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "escape", 0, 2)]
        _, state = _start_combat_encounter(mode="stealth", objectives=objectives)
        action = {"metadata": {"encounter_action_type": "move_quietly"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert any(u.get("progress", 0) > 0 for u in result.objective_updates)

    def test_distract_sets_alert_distracted(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="stealth")
        action = {"metadata": {"encounter_action_type": "distract"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("mode_state", {}).get("alert_level") == "distracted"

    def test_retreat_resolves(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="stealth")
        action = {"metadata": {"encounter_action_type": "retreat"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.outcome_type == "resolve"

    def test_observe_patrol_sets_watching(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="stealth")
        action = {"metadata": {"encounter_action_type": "observe_patrol"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("mode_state", {}).get("alert_level") == "watching"


class TestResolverInvestigationMode:
    """Investigation-mode resolution tests."""

    def test_inspect_area_progresses_investigate(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "investigate", 0, 3)]
        _, state = _start_combat_encounter(mode="investigation", objectives=objectives)
        action = {"metadata": {"encounter_action_type": "inspect_area"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert any(u.get("progress", 0) > 0 for u in result.objective_updates)

    def test_question_witness_updates_lead_targets(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="investigation")
        action = {"metadata": {"encounter_action_type": "question_witness", "target_id": "witness1"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        lead = result.state_updates.get("mode_state", {}).get("lead_targets")
        assert lead is not None

    def test_follow_lead_progresses(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "investigate", 0, 3)]
        _, state = _start_combat_encounter(mode="investigation", objectives=objectives)
        action = {"metadata": {"encounter_action_type": "follow_lead"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert any(u.get("progress", 0) > 0 for u in result.objective_updates)

    def test_test_theory_updates_clue_progress(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="investigation")
        action = {"metadata": {"encounter_action_type": "test_theory"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        clue = result.state_updates.get("mode_state", {}).get("clue_progress", {})
        assert clue.get("theory_tested") is True


class TestResolverDiplomacyMode:
    """Diplomacy-mode resolution tests."""

    def test_make_offer_progresses_convince(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "convince", 0, 2)]
        _, state = _start_combat_encounter(mode="diplomacy", objectives=objectives)
        action = {"metadata": {"encounter_action_type": "make_offer"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert any(u.get("progress", 0) > 0 for u in result.objective_updates)

    def test_threaten_raises_pressure(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="diplomacy")
        action = {"metadata": {"encounter_action_type": "threaten"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("pressure") == "rising"

    def test_stall_thins_patience(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="diplomacy")
        action = {"metadata": {"encounter_action_type": "stall"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("mode_state", {}).get("patience") == "thinning"

    def test_concede_point_updates_concession(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="diplomacy")
        action = {"metadata": {"encounter_action_type": "concede_point"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("mode_state", {}).get("concession_count") == 1

    def test_convince_completion_resolves(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "convince", progress=1, required=2)]
        _, state = _start_combat_encounter(mode="diplomacy", objectives=objectives)
        action = {"metadata": {"encounter_action_type": "make_offer"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.outcome_type == "resolve"


class TestResolverChaseMode:
    """Chase-mode resolution tests."""

    def test_sprint_progresses_escape(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "escape", 0, 3)]
        _, state = _start_combat_encounter(mode="chase", objectives=objectives)
        action = {"metadata": {"encounter_action_type": "sprint"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert any(u.get("progress", 0) > 0 for u in result.objective_updates)

    def test_evade_obstacle_widens_distance(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="chase")
        action = {"metadata": {"encounter_action_type": "evade_obstacle"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("mode_state", {}).get("distance_band") == "widening"

    def test_cut_off_route_closes_distance(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="chase")
        action = {"metadata": {"encounter_action_type": "cut_off_route"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.state_updates.get("mode_state", {}).get("distance_band") == "closing"

    def test_hide_resolves(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="chase")
        action = {"metadata": {"encounter_action_type": "hide"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.outcome_type == "resolve"

    def test_force_confrontation_escalates(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter(mode="chase")
        action = {"metadata": {"encounter_action_type": "force_confrontation"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.outcome_type == "escalate"

    def test_maintain_pursuit_progresses_capture(self):
        resolver = EncounterResolver()
        objectives = [_make_objective("obj-1", "capture", 0, 2)]
        _, state = _start_combat_encounter(mode="chase", objectives=objectives)
        action = {"metadata": {"encounter_action_type": "maintain_pursuit"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert any(u.get("progress", 0) > 0 for u in result.objective_updates)


class TestResolverJournalPayload:
    """Resolver journal payload tests."""

    def test_resolve_action_produces_journal_payload(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "withdraw"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.journal_payload.get("journalable") is True

    def test_continue_action_no_journal_payload(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "defend"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.journal_payload.get("journalable") is not True

    def test_resolve_journal_kind(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "withdraw"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.journal_payload.get("kind") == "encounter_resolved"


class TestResolverTrace:
    """Resolver trace output tests."""

    def test_trace_contains_mode(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "strike"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.trace.get("mode") == "combat"

    def test_trace_contains_action_type(self):
        resolver = EncounterResolver()
        _, state = _start_combat_encounter()
        action = {"metadata": {"encounter_action_type": "strike"}}
        result = resolver.resolve_action(state, action, _scene_summary())
        assert result.trace.get("action_type") == "strike"


# ======================================================================
# Presenter tests
# ======================================================================

class TestPresenterPresentEncounter:
    """EncounterPresenter.present_encounter tests."""

    def test_returns_empty_for_none(self):
        presenter = EncounterPresenter()
        assert presenter.present_encounter(None) == {}

    def test_returns_complete_payload(self):
        presenter = EncounterPresenter()
        _, state = _start_combat_encounter()
        payload = presenter.present_encounter(state)
        assert "encounter_id" in payload
        assert "mode" in payload
        assert "status" in payload
        assert "round_index" in payload
        assert "participants" in payload
        assert "objectives" in payload
        assert "pressure" in payload
        assert "stakes" in payload

    def test_participant_summaries_present(self):
        presenter = EncounterPresenter()
        _, state = _start_combat_encounter()
        payload = presenter.present_encounter(state)
        assert len(payload["participants"]) == len(state.participants)
        first = payload["participants"][0]
        assert "entity_id" in first
        assert "role" in first
        assert "status" in first

    def test_objective_summaries_present(self):
        presenter = EncounterPresenter()
        _, state = _start_combat_encounter()
        payload = presenter.present_encounter(state)
        assert len(payload["objectives"]) == len(state.objectives)


class TestPresenterPresentEncounterTrace:
    """EncounterPresenter.present_encounter_trace tests."""

    def test_returns_empty_for_none(self):
        presenter = EncounterPresenter()
        assert presenter.present_encounter_trace(None) == {}

    def test_returns_trace_payload(self):
        presenter = EncounterPresenter()
        resolution = EncounterResolution(
            mode="combat",
            outcome_type="continue",
            trace={"reason": "test"},
            participant_updates=[{"entity_id": "e1", "status": "engaged"}],
            objective_updates=[{"objective_id": "o1", "progress": 1}],
            state_updates={"advance_turn": True},
        )
        payload = presenter.present_encounter_trace(resolution)
        assert payload["mode"] == "combat"
        assert payload["outcome_type"] == "continue"
        assert len(payload["participant_updates"]) == 1
        assert len(payload["objective_updates"]) == 1


class TestPresenterPresentJournalPayload:
    """EncounterPresenter.present_journal_payload tests."""

    def test_returns_empty_for_none(self):
        presenter = EncounterPresenter()
        assert presenter.present_journal_payload(None) == {}

    def test_returns_empty_for_non_journalable(self):
        presenter = EncounterPresenter()
        res = EncounterResolution(journal_payload={})
        assert presenter.present_journal_payload(res) == {}

    def test_returns_empty_for_non_journalable_flag_false(self):
        presenter = EncounterPresenter()
        res = EncounterResolution(journal_payload={"journalable": False})
        assert presenter.present_journal_payload(res) == {}

    def test_returns_empty_for_unrecognized_kind(self):
        presenter = EncounterPresenter()
        res = EncounterResolution(
            journal_payload={"journalable": True, "kind": "some_random_kind"}
        )
        assert presenter.present_journal_payload(res) == {}

    def test_returns_payload_for_encounter_resolved(self):
        presenter = EncounterPresenter()
        res = EncounterResolution(
            journal_payload={
                "journalable": True,
                "kind": "encounter_resolved",
                "encounter_id": "e1",
                "mode": "combat",
                "action": "withdraw",
                "outcome_type": "resolve",
            }
        )
        payload = presenter.present_journal_payload(res)
        assert payload != {}
        assert payload["kind"] == "encounter_resolved"
        assert payload["encounter_id"] == "e1"
        assert "summary" in payload

    def test_returns_payload_for_encounter_started(self):
        presenter = EncounterPresenter()
        res = EncounterResolution(
            journal_payload={
                "journalable": True,
                "kind": "encounter_started",
                "encounter_id": "e2",
                "mode": "stealth",
                "action": "sneak",
                "outcome_type": "resolve",
            }
        )
        payload = presenter.present_journal_payload(res)
        assert payload != {}
        assert payload["kind"] == "encounter_started"


# ======================================================================
# Journal builder tests
# ======================================================================

class TestJournalBuilderEncounterLogEntry:
    """JournalBuilder.build_encounter_log_entry tests."""

    def test_returns_none_for_non_journalable_kind(self):
        builder = JournalBuilder()
        log = {"kind": "routine_action", "encounter_id": "e1"}
        result = builder.build_encounter_log_entry(log)
        assert result is None

    def test_returns_none_for_empty_kind(self):
        builder = JournalBuilder()
        log = {"kind": "", "encounter_id": "e1"}
        result = builder.build_encounter_log_entry(log)
        assert result is None

    def test_returns_none_for_missing_kind(self):
        builder = JournalBuilder()
        log = {"encounter_id": "e1"}
        result = builder.build_encounter_log_entry(log)
        assert result is None

    def test_returns_entry_for_encounter_resolved(self):
        builder = JournalBuilder()
        log = {
            "kind": "encounter_resolved",
            "encounter_id": "e1",
            "mode": "combat",
            "action": "withdraw",
            "summary": "The battle ended.",
        }
        result = builder.build_encounter_log_entry(log, tick=5, location="forest")
        assert result is not None
        assert result.entry_type == "encounter"
        assert result.tick == 5
        assert result.location == "forest"

    def test_returns_entry_for_encounter_started(self):
        builder = JournalBuilder()
        log = {"kind": "encounter_started", "encounter_id": "e2", "mode": "stealth"}
        result = builder.build_encounter_log_entry(log, tick=1)
        assert result is not None
        assert result.entry_type == "encounter"

    def test_returns_entry_for_objective_completed(self):
        builder = JournalBuilder()
        log = {"kind": "objective_completed", "encounter_id": "e1", "mode": "investigation"}
        result = builder.build_encounter_log_entry(log)
        assert result is not None

    def test_returns_entry_for_objective_failed(self):
        builder = JournalBuilder()
        log = {"kind": "objective_failed", "encounter_id": "e1"}
        result = builder.build_encounter_log_entry(log)
        assert result is not None

    def test_entry_id_is_deterministic(self):
        builder = JournalBuilder()
        log = {"kind": "encounter_resolved", "encounter_id": "e1"}
        r1 = builder.build_encounter_log_entry(log, tick=3)
        r2 = builder.build_encounter_log_entry(log, tick=3)
        assert r1.entry_id == r2.entry_id

    def test_entry_id_varies_with_tick(self):
        builder = JournalBuilder()
        log = {"kind": "encounter_resolved", "encounter_id": "e1"}
        r1 = builder.build_encounter_log_entry(log, tick=1)
        r2 = builder.build_encounter_log_entry(log, tick=2)
        assert r1.entry_id != r2.entry_id

    def test_metadata_contains_source(self):
        builder = JournalBuilder()
        log = {"kind": "encounter_resolved", "encounter_id": "e1", "mode": "chase"}
        result = builder.build_encounter_log_entry(log)
        assert result.metadata.get("source") == "encounter_log"
        assert result.metadata.get("encounter_id") == "e1"
        assert result.metadata.get("mode") == "chase"

    def test_summary_uses_provided_value(self):
        builder = JournalBuilder()
        log = {
            "kind": "encounter_resolved",
            "encounter_id": "e1",
            "mode": "combat",
            "summary": "Custom summary text",
        }
        result = builder.build_encounter_log_entry(log)
        assert result.summary == "Custom summary text"

    def test_summary_fallback_when_missing(self):
        builder = JournalBuilder()
        log = {"kind": "encounter_resolved", "encounter_id": "e1", "mode": "combat"}
        result = builder.build_encounter_log_entry(log)
        assert "encounter_resolved" in result.summary
        assert "combat" in result.summary

    def test_all_journalable_kinds_accepted(self):
        builder = JournalBuilder()
        journalable_kinds = [
            "encounter_started", "encounter_resolved",
            "objective_completed", "objective_failed",
            "combat_turning_point", "stealth_exposed",
            "investigation_breakthrough", "diplomacy_breakthrough",
            "chase_outcome",
        ]
        for kind in journalable_kinds:
            log = {"kind": kind, "encounter_id": "e1", "mode": "combat"}
            result = builder.build_encounter_log_entry(log)
            assert result is not None, f"Expected entry for kind={kind}"


# ======================================================================
# Memory core tests
# ======================================================================

class TestCampaignMemoryCoreEncounterRecording:
    """CampaignMemoryCore.record_encounter_log_entry tests."""

    def test_records_meaningful_entry(self):
        core = CampaignMemoryCore()
        log = {
            "kind": "encounter_resolved",
            "encounter_id": "e1",
            "mode": "combat",
            "summary": "The battle is over.",
        }
        before = len(core.journal_entries)
        core.record_encounter_log_entry(log, tick=10, location="cave")
        assert len(core.journal_entries) == before + 1

    def test_ignores_non_meaningful_entry(self):
        core = CampaignMemoryCore()
        log = {"kind": "routine_action", "encounter_id": "e1"}
        before = len(core.journal_entries)
        core.record_encounter_log_entry(log, tick=10)
        assert len(core.journal_entries) == before

    def test_entry_has_correct_type(self):
        core = CampaignMemoryCore()
        log = {"kind": "encounter_resolved", "encounter_id": "e1", "mode": "stealth"}
        core.record_encounter_log_entry(log, tick=5)
        assert core.journal_entries[-1].entry_type == "encounter"

    def test_entry_preserves_location(self):
        core = CampaignMemoryCore()
        log = {"kind": "encounter_started", "encounter_id": "e1", "mode": "chase"}
        core.record_encounter_log_entry(log, tick=1, location="harbor")
        assert core.journal_entries[-1].location == "harbor"

    def test_multiple_entries_accumulate(self):
        core = CampaignMemoryCore()
        for i in range(5):
            log = {"kind": "encounter_resolved", "encounter_id": f"e{i}", "mode": "combat"}
            core.record_encounter_log_entry(log, tick=i)
        assert len(core.journal_entries) == 5

    def test_trim_respects_max_entries(self):
        core = CampaignMemoryCore()
        core._max_entries = 10
        for i in range(15):
            log = {"kind": "encounter_resolved", "encounter_id": f"e{i}", "mode": "combat"}
            core.record_encounter_log_entry(log, tick=i)
        assert len(core.journal_entries) <= 10
