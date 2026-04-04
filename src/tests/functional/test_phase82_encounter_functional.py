"""Phase 8.2 — Encounter Functional Tests.

Integration scenarios across EncounterController, EncounterResolver,
EncounterPresenter, JournalBuilder, and CampaignMemoryCore.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.rpg.encounter.controller import EncounterController
from app.rpg.encounter.resolver import EncounterResolver
from app.rpg.encounter.presenter import EncounterPresenter
from app.rpg.encounter.models import (
    EncounterResolution,
    EncounterState,
    SUPPORTED_ENCOUNTER_MODES,
)
from app.rpg.memory.journal_builder import JournalBuilder
from app.rpg.memory.core import CampaignMemoryCore


# ======================================================================
# Test helpers / fixtures
# ======================================================================

def _scene(location: str = "forest_clearing") -> dict:
    return {"location": location, "summary": "A tense clearing.", "present_actors": []}


def _participants_combat() -> list[dict]:
    return [
        {"entity_id": "player", "role": "player", "team": "party"},
        {"entity_id": "goblin_1", "role": "enemy", "team": "enemies"},
    ]


def _participants_stealth() -> list[dict]:
    return [
        {"entity_id": "player", "role": "player", "team": "party"},
        {"entity_id": "guard_1", "role": "enemy", "team": "patrol"},
    ]


def _participants_diplomacy() -> list[dict]:
    return [
        {"entity_id": "player", "role": "player", "team": "party"},
        {"entity_id": "envoy", "role": "neutral", "team": "delegation"},
    ]


def _objective_defeat(required: int = 2) -> list[dict]:
    return [{"objective_id": "obj_defeat", "kind": "defeat", "required": required}]


def _objective_escape(required: int = 2) -> list[dict]:
    return [{"objective_id": "obj_escape", "kind": "escape", "required": required}]


def _objective_convince(required: int = 2) -> list[dict]:
    return [{"objective_id": "obj_convince", "kind": "convince", "required": required}]


def _strike_action(target_id: str = "goblin_1") -> dict:
    return {
        "intent_type": "strike",
        "target_id": target_id,
        "metadata": {"encounter_action_type": "strike"},
    }


def _defend_action() -> dict:
    return {"intent_type": "defend", "metadata": {"encounter_action_type": "defend"}}


def _slip_through_action() -> dict:
    return {
        "intent_type": "slip_through",
        "metadata": {"encounter_action_type": "slip_through"},
    }


def _make_offer_action() -> dict:
    return {
        "intent_type": "make_offer",
        "metadata": {"encounter_action_type": "make_offer"},
    }


def _start_combat(ctrl: EncounterController, **kw) -> EncounterState:
    return ctrl.start_encounter(
        mode="combat",
        scene_summary=kw.get("scene", _scene()),
        participants=kw.get("participants", _participants_combat()),
        objectives=kw.get("objectives", _objective_defeat()),
        tick=kw.get("tick", 1),
    )


def _start_stealth(ctrl: EncounterController, **kw) -> EncounterState:
    return ctrl.start_encounter(
        mode="stealth",
        scene_summary=kw.get("scene", _scene()),
        participants=kw.get("participants", _participants_stealth()),
        objectives=kw.get("objectives", _objective_escape()),
        tick=kw.get("tick", 1),
    )


def _start_diplomacy(ctrl: EncounterController, **kw) -> EncounterState:
    return ctrl.start_encounter(
        mode="diplomacy",
        scene_summary=kw.get("scene", _scene()),
        participants=kw.get("participants", _participants_diplomacy()),
        objectives=kw.get("objectives", _objective_convince()),
        tick=kw.get("tick", 1),
    )


# ======================================================================
# 1. Encounter-start option activates encounter
# ======================================================================

class TestEncounterStartActivation:
    """Choosing a start option activates the encounter with correct mode."""

    def test_combat_start_option_activates_encounter(self):
        ctrl = EncounterController()
        state = _start_combat(ctrl)

        assert ctrl.has_active_encounter()
        assert state.status == "active"
        assert state.mode == "combat"

    def test_stealth_start_option_activates_encounter(self):
        ctrl = EncounterController()
        state = _start_stealth(ctrl)

        assert ctrl.has_active_encounter()
        assert state.status == "active"
        assert state.mode == "stealth"

    def test_scene_data_includes_encounter_payload(self):
        ctrl = EncounterController()
        presenter = EncounterPresenter()
        _start_combat(ctrl)

        payload = presenter.present_encounter(ctrl.get_active_encounter())

        assert payload["encounter_id"]
        assert payload["mode"] == "combat"
        assert payload["status"] == "active"
        assert isinstance(payload["participants"], list)
        assert len(payload["participants"]) >= 2


# ======================================================================
# 2. Active encounter changes option generation
# ======================================================================

class TestActiveEncounterOptionGeneration:
    """Active encounter supplies mode-specific choice context."""

    def test_combat_encounter_provides_tactical_options(self):
        ctrl = EncounterController()
        _start_combat(ctrl)

        ctx = ctrl.build_choice_context(player_id="player")

        assert ctx is not None
        assert ctx.mode == "combat"
        assert "strike" in ctx.available_actions
        assert "defend" in ctx.available_actions

    def test_stealth_encounter_provides_stealth_options(self):
        ctrl = EncounterController()
        _start_stealth(ctrl)

        ctx = ctrl.build_choice_context(player_id="player")

        assert ctx is not None
        assert ctx.mode == "stealth"
        assert "stay_hidden" in ctx.available_actions
        assert "move_quietly" in ctx.available_actions

    def test_no_encounter_returns_none_context(self):
        ctrl = EncounterController()

        ctx = ctrl.build_choice_context(player_id="player")

        assert ctx is None


# ======================================================================
# 3. Encounter resolution updates state
# ======================================================================

class TestEncounterResolutionUpdatesState:
    """Resolver produces resolutions that update controller state."""

    def test_tactical_action_updates_participants(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()
        state = _start_combat(ctrl)

        resolution = resolver.resolve_action(
            encounter_state=state,
            resolved_action=_strike_action("goblin_1"),
            scene_summary=_scene(),
            tick=2,
        )
        assert resolution is not None
        ctrl.apply_resolution(resolution)

        updated = ctrl.get_active_encounter()
        goblin = next(p for p in updated.participants if p.entity_id == "goblin_1")
        assert goblin.status == "engaged"

    def test_enough_actions_complete_objective(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()
        state = _start_combat(ctrl, objectives=_objective_defeat(required=2))

        for _ in range(2):
            res = resolver.resolve_action(
                encounter_state=ctrl.get_active_encounter(),
                resolved_action=_strike_action(),
                scene_summary=_scene(),
            )
            assert res is not None
            ctrl.apply_resolution(res)

        updated = ctrl.get_active_encounter()
        assert updated.status == "resolved"
        obj = next(o for o in updated.objectives if o.objective_id == "obj_defeat")
        assert obj.status == "completed"

    def test_resolution_advances_round_turn(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()
        _start_combat(ctrl)

        assert ctrl.get_active_encounter().turn_index == 0
        assert ctrl.get_active_encounter().round_index == 0

        res = resolver.resolve_action(
            encounter_state=ctrl.get_active_encounter(),
            resolved_action=_defend_action(),
            scene_summary=_scene(),
        )
        ctrl.apply_resolution(res)

        updated = ctrl.get_active_encounter()
        assert updated.turn_index > 0 or updated.round_index > 0


# ======================================================================
# 4. Meaningful encounter outcome journals
# ======================================================================

class TestEncounterOutcomeJournals:
    """Encounter events produce journal entries only for meaningful outcomes."""

    def test_resolve_outcome_creates_journal_entry(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()
        presenter = EncounterPresenter()
        memory = CampaignMemoryCore()

        _start_combat(ctrl, objectives=_objective_defeat(required=1))

        res = resolver.resolve_action(
            encounter_state=ctrl.get_active_encounter(),
            resolved_action=_strike_action(),
            scene_summary=_scene(),
            tick=5,
        )
        ctrl.apply_resolution(res)

        journal_payload = presenter.present_journal_payload(res, ctrl.get_active_encounter())
        assert journal_payload.get("kind") == "encounter_resolved"

        memory.record_encounter_log_entry(journal_payload, tick=5, location="forest_clearing")
        assert len(memory.journal_entries) == 1
        assert memory.journal_entries[0].entry_type == "encounter"

    def test_non_resolve_action_no_journal(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()
        presenter = EncounterPresenter()

        _start_combat(ctrl, objectives=_objective_defeat(required=5))

        res = resolver.resolve_action(
            encounter_state=ctrl.get_active_encounter(),
            resolved_action=_defend_action(),
            scene_summary=_scene(),
        )
        ctrl.apply_resolution(res)

        journal_payload = presenter.present_journal_payload(res)
        assert journal_payload == {}

    def test_journal_entry_has_encounter_metadata(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()
        presenter = EncounterPresenter()
        memory = CampaignMemoryCore()

        state = _start_combat(ctrl, objectives=_objective_defeat(required=1))

        res = resolver.resolve_action(
            encounter_state=ctrl.get_active_encounter(),
            resolved_action=_strike_action(),
            scene_summary=_scene(),
            tick=10,
        )
        ctrl.apply_resolution(res)

        journal_payload = presenter.present_journal_payload(res, ctrl.get_active_encounter())
        memory.record_encounter_log_entry(journal_payload, tick=10, location="forest_clearing")

        entry = memory.journal_entries[0]
        assert entry.metadata["encounter_id"] == state.encounter_id
        assert entry.metadata["mode"] == "combat"
        assert entry.metadata["kind"] == "encounter_resolved"


# ======================================================================
# 5. Diplomacy encounter coexists with other state
# ======================================================================

class TestDiplomacyEncounterCoexistence:
    """Diplomacy mode encounter payloads carry correct structure."""

    def test_diplomacy_payload_has_correct_mode(self):
        ctrl = EncounterController()
        presenter = EncounterPresenter()
        _start_diplomacy(ctrl)

        payload = presenter.present_encounter(ctrl.get_active_encounter())

        assert payload["mode"] == "diplomacy"
        assert payload["status"] == "active"

    def test_diplomacy_payload_includes_objectives_and_participants(self):
        ctrl = EncounterController()
        presenter = EncounterPresenter()
        _start_diplomacy(ctrl)

        payload = presenter.present_encounter(ctrl.get_active_encounter())

        assert len(payload["objectives"]) >= 1
        assert payload["objectives"][0]["kind"] == "convince"
        assert len(payload["participants"]) >= 2

    def test_diplomacy_presenter_produces_mode_state_summary(self):
        ctrl = EncounterController()
        presenter = EncounterPresenter()
        _start_diplomacy(ctrl)

        payload = presenter.present_encounter(ctrl.get_active_encounter())

        assert isinstance(payload, dict)
        assert "mode_state_summary" in payload
        assert isinstance(payload["mode_state_summary"], dict)
        assert "patience" in payload["mode_state_summary"]


# ======================================================================
# 6. End-to-end flow
# ======================================================================

class TestEndToEndFlow:
    """Full lifecycle and serialization round-trips."""

    def test_full_flow_start_action_resolve_present(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()
        presenter = EncounterPresenter()

        _start_combat(ctrl, objectives=_objective_defeat(required=1))
        assert ctrl.has_active_encounter()

        res = resolver.resolve_action(
            encounter_state=ctrl.get_active_encounter(),
            resolved_action=_strike_action(),
            scene_summary=_scene(),
            tick=3,
        )
        ctrl.apply_resolution(res)

        payload = presenter.present_encounter(ctrl.get_active_encounter())
        assert payload["status"] == "resolved"
        assert payload["mode"] == "combat"

    def test_snapshot_roundtrip_preserves_encounter(self):
        ctrl = EncounterController()
        state = _start_combat(ctrl, tick=7)

        snapshot = ctrl.to_dict()
        restored = EncounterController.from_dict(snapshot)

        assert restored.has_active_encounter()
        rs = restored.get_active_encounter()
        assert rs.encounter_id == state.encounter_id
        assert rs.mode == state.mode
        assert rs.status == state.status
        assert len(rs.participants) == len(state.participants)
        assert len(rs.objectives) == len(state.objectives)

    def test_multiple_modes_in_sequence(self):
        ctrl = EncounterController()
        resolver = EncounterResolver()

        # Start and resolve combat
        _start_combat(ctrl, objectives=_objective_defeat(required=1), tick=1)
        res = resolver.resolve_action(
            encounter_state=ctrl.get_active_encounter(),
            resolved_action=_strike_action(),
            scene_summary=_scene(),
        )
        ctrl.apply_resolution(res)
        assert ctrl.get_active_encounter().status == "resolved"

        # Clear and start stealth
        ctrl.clear_encounter()
        assert not ctrl.has_active_encounter()

        _start_stealth(ctrl, tick=2)
        assert ctrl.has_active_encounter()
        assert ctrl.get_active_encounter().mode == "stealth"
