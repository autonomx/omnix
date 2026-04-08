"""Phase 8.4 — Debug / Analytics / GM Inspection — Functional Tests.

End-to-end integration tests verifying that debug flows work correctly
when multiple subsystems are combined: UX payload building, GM inspection
bundles, trace construction, and presentation.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/functional/test_phase84_debug_functional.py -v --noconftest
"""

from __future__ import annotations

import copy

import pytest

from app.rpg.debug.core import DebugCore
from app.rpg.debug.models import (
    SUPPORTED_DEBUG_NODE_TYPES,
    SUPPORTED_DEBUG_SCOPES,
    ChoiceExplanation,
    DebugTrace,
    DebugTraceNode,
    EncounterExplanation,
    GMInspectionBundle,
    NPCResponseExplanation,
    WorldSimExplanation,
)
from app.rpg.debug.presenter import DebugPresenter
from app.rpg.debug.trace_builder import DebugTraceBuilder
from app.rpg.ux.models import ActionResultPayload, PlayerChoiceCard, SceneUXPayload
from app.rpg.ux.payload_builder import UXPayloadBuilder
from app.rpg.ux.presenters import UXPresenter

# ======================================================================
# Helpers — lightweight mock loop
# ======================================================================

class _MockGameplayController:
    """Minimal gameplay controller stub."""

    def __init__(self, last_choice_set: dict | None = None) -> None:
        self._last = last_choice_set

    def get_last_choice_set(self) -> dict | None:
        return self._last

    def select_option(self, option_id: str) -> dict | None:
        if self._last is None:
            return None
        for opt in self._last.get("options", []):
            if opt.get("option_id") == option_id:
                return dict(opt)
        return None


class _MinimalLoop:
    """Simulates a GameLoop with only the attributes that UXPayloadBuilder reads."""

    def __init__(
        self,
        tick_count: int = 5,
        coherence_core=None,
        gameplay_control_controller=None,
        last_debug_bundle: dict | None = None,
        last_dialogue_response: dict | None = None,
        encounter_controller=None,
        encounter_presenter=None,
        world_sim_controller=None,
        world_sim_presenter=None,
        campaign_memory_core=None,
        social_state_core=None,
        arc_control_controller=None,
        pack_registry=None,
    ) -> None:
        self.tick_count = tick_count
        self.coherence_core = coherence_core
        self.gameplay_control_controller = gameplay_control_controller
        self.last_debug_bundle = last_debug_bundle
        self.last_dialogue_response = last_dialogue_response
        self.encounter_controller = encounter_controller
        self.encounter_presenter = encounter_presenter
        self.world_sim_controller = world_sim_controller
        self.world_sim_presenter = world_sim_presenter
        self.campaign_memory_core = campaign_memory_core
        self.social_state_core = social_state_core
        self.arc_control_controller = arc_control_controller
        self.pack_registry = pack_registry


# ======================================================================
# Shared sample data factories
# ======================================================================

def _sample_choice_set() -> dict:
    return {
        "options": [
            {
                "option_id": "opt_1",
                "label": "Attack",
                "summary": "Charge into battle",
                "intent_type": "combat",
                "target_id": "goblin",
                "tags": ["combat"],
                "priority": 2.0,
            },
            {
                "option_id": "opt_2",
                "label": "Negotiate",
                "summary": "Try diplomacy",
                "intent_type": "social_contact",
                "target_id": "goblin",
                "tags": ["social"],
                "priority": 1.0,
            },
        ],
    }


def _sample_debug_bundle() -> dict:
    return {
        "tick": 5,
        "choices": [
            {"choice_id": "opt_1", "label": "Attack"},
            {"choice_id": "opt_2", "label": "Negotiate"},
        ],
        "warnings": ["low coherence at tick 4"],
        "dialogue_summary": {"speaker_id": "npc1", "act": "refuse"},
        "encounter_summary": {"encounter_id": "enc1", "mode": "combat"},
        "world_summary": {"sim_tick": 5, "effect_count": 2},
    }


def _sample_dialogue_response() -> dict:
    return {
        "speaker_id": "npc1",
        "listener_id": "player",
        "act": "refuse",
        "tone": "hostile",
        "stance": "defensive",
        "summary": "NPC refuses",
    }


def _sample_dialogue_trace() -> dict:
    return {
        "decision_reasons": ["low_trust", "hostile_stance"],
        "state_drivers": {"trust": -0.5},
        "primary_act": "refuse",
        "reveal_policy": {"blocked_topics": ["secret_base"]},
    }


def _sample_encounter_state() -> dict:
    return {
        "encounter_id": "enc1",
        "mode": "combat",
        "status": "active",
        "pressure": 0.7,
        "stakes": "high",
        "round_index": 2,
    }


def _sample_encounter_resolution() -> dict:
    return {
        "mode": "combat",
        "outcome_type": "ongoing",
        "reasons": "combat continues",
        "participant_updates": [{"entity_id": "npc1", "status": "active"}],
        "objective_updates": [],
        "state_updates": {},
    }


def _sample_world_sim_result() -> dict:
    return {
        "tick": 5,
        "advanced": True,
        "generated_effects": [
            {"effect_type": "faction_shift", "scope": "world", "target_id": "guild_a"},
            {"effect_type": "rumor_spread", "scope": "local", "target_id": "rumor_1"},
        ],
        "generated_summaries": [],
        "journal_payloads": [],
    }


def _sample_arc_debug_summary() -> dict:
    return {
        "active_arcs": [{"arc_id": "a1", "title": "Main Quest", "status": "active"}],
        "active_arc_count": 1,
        "reveal_pressure": "high",
        "pacing_pressure": "normal",
    }


def _sample_recovery_debug_summary() -> dict:
    return {
        "recent_recoveries": [
            {"recovery_id": "r1", "reason": "contradiction", "tick": 3, "summary": "Fixed"},
        ],
        "warnings": ["Contradiction at tick 3"],
        "total_recovery_count": 1,
    }


# ======================================================================
# 1. Scene payload includes debug summary
# ======================================================================

class TestScenePayloadIncludesDebugSummary:
    """Verify that building a scene payload embeds a compact debug dict."""

    def test_scene_payload_has_debug_when_bundle_present(self) -> None:
        loop = _MinimalLoop(
            tick_count=5,
            gameplay_control_controller=_MockGameplayController(_sample_choice_set()),
            last_debug_bundle=_sample_debug_bundle(),
        )
        payload = UXPayloadBuilder().build_scene_payload(loop)
        assert isinstance(payload, SceneUXPayload)
        assert payload.debug, "debug dict should not be empty"

    def test_scene_debug_has_tick(self) -> None:
        loop = _MinimalLoop(
            tick_count=5,
            gameplay_control_controller=_MockGameplayController(_sample_choice_set()),
            last_debug_bundle=_sample_debug_bundle(),
        )
        payload = UXPayloadBuilder().build_scene_payload(loop)
        assert payload.debug.get("tick") == 5

    def test_scene_debug_has_choice_count(self) -> None:
        loop = _MinimalLoop(
            tick_count=5,
            gameplay_control_controller=_MockGameplayController(_sample_choice_set()),
            last_debug_bundle=_sample_debug_bundle(),
        )
        payload = UXPayloadBuilder().build_scene_payload(loop)
        assert payload.debug.get("choice_count") == 2

    def test_scene_debug_has_warning_count(self) -> None:
        loop = _MinimalLoop(
            tick_count=5,
            gameplay_control_controller=_MockGameplayController(_sample_choice_set()),
            last_debug_bundle=_sample_debug_bundle(),
        )
        payload = UXPayloadBuilder().build_scene_payload(loop)
        assert payload.debug.get("warning_count") == 1

    def test_scene_debug_is_bounded(self) -> None:
        loop = _MinimalLoop(
            tick_count=5,
            gameplay_control_controller=_MockGameplayController(_sample_choice_set()),
            last_debug_bundle=_sample_debug_bundle(),
        )
        payload = UXPayloadBuilder().build_scene_payload(loop)
        # Debug dict should be compact — a handful of keys, not a full trace dump
        assert len(payload.debug) <= 10, "debug summary should have few keys"


# ======================================================================
# 2. Action result includes debug bundle
# ======================================================================

class TestActionResultIncludesDebugBundle:
    """Verify that action-result payloads carry a compact debug summary."""

    def _build_action_result_payload(self) -> ActionResultPayload:
        loop = _MinimalLoop(
            tick_count=5,
            gameplay_control_controller=_MockGameplayController(_sample_choice_set()),
            last_debug_bundle=_sample_debug_bundle(),
        )
        action_result = {
            "choice_id": "opt_1",
            "resolved_action": {
                "action_id": "act_1",
                "intent_type": "combat",
                "target_id": "goblin",
                "outcome": "hit",
                "summary": "Attacked goblin",
                "metadata": {},
            },
            "events": [],
        }
        return UXPayloadBuilder().build_action_result_payload(loop, action_result)

    def test_action_result_has_debug(self) -> None:
        payload = self._build_action_result_payload()
        assert isinstance(payload, ActionResultPayload)
        assert payload.debug, "action result debug should not be empty"

    def test_action_result_debug_has_tick(self) -> None:
        payload = self._build_action_result_payload()
        assert payload.debug.get("tick") == 5

    def test_action_result_debug_has_choice_count(self) -> None:
        payload = self._build_action_result_payload()
        assert payload.debug.get("choice_count") == 2

    def test_action_result_debug_is_compact(self) -> None:
        payload = self._build_action_result_payload()
        assert len(payload.debug) <= 10


# ======================================================================
# 3. Dialogue + encounter + world are all inspectable together
# ======================================================================

class TestAllSubsystemsInspectable:
    """Build a GM bundle with dialogue, encounter, and world data and
    verify all three explanation sections are populated and independent."""

    def _build_full_gm_bundle(self) -> dict:
        core = DebugCore()
        return core.build_gm_inspection_bundle(
            tick=5,
            last_dialogue_response=_sample_dialogue_response(),
            last_dialogue_trace=_sample_dialogue_trace(),
            last_encounter_state=_sample_encounter_state(),
            last_encounter_resolution=_sample_encounter_resolution(),
            last_world_sim_result=_sample_world_sim_result(),
        )

    def test_all_three_sections_non_empty(self) -> None:
        bundle = self._build_full_gm_bundle()
        assert bundle.get("dialogue_summary"), "dialogue section should be populated"
        assert bundle.get("encounter_summary"), "encounter section should be populated"
        assert bundle.get("world_summary"), "world section should be populated"

    def test_dialogue_summary_fields(self) -> None:
        bundle = self._build_full_gm_bundle()
        dlg = bundle["dialogue_summary"]
        assert dlg["speaker_id"] == "npc1"
        assert dlg["act"] == "refuse"
        assert dlg["tone"] == "hostile"
        assert dlg["stance"] == "defensive"
        # Reasons extracted from trace
        assert dlg.get("reason_count", 0) > 0 or len(dlg.get("reasons", [])) > 0

    def test_encounter_summary_fields(self) -> None:
        bundle = self._build_full_gm_bundle()
        enc = bundle["encounter_summary"]
        assert enc["encounter_id"] == "enc1"
        assert enc["mode"] == "combat"
        assert enc["outcome_type"] == "ongoing"
        assert enc.get("reason_count", 0) > 0 or len(enc.get("reasons", [])) > 0

    def test_world_summary_fields(self) -> None:
        bundle = self._build_full_gm_bundle()
        ws = bundle["world_summary"]
        assert ws["sim_tick"] == 5
        assert ws["effect_count"] == 2
        assert ws.get("reason_count", 0) > 0 or len(ws.get("reasons", [])) > 0

    def test_sections_do_not_overwrite_each_other(self) -> None:
        bundle = self._build_full_gm_bundle()
        # Each section is a distinct dict at a distinct key
        dlg = bundle.get("dialogue_summary", {})
        enc = bundle.get("encounter_summary", {})
        ws = bundle.get("world_summary", {})
        # They should not share identity
        assert dlg is not enc
        assert enc is not ws
        assert dlg is not ws


# ======================================================================
# 4. Recovery / arc summaries appear when present
# ======================================================================

class TestRecoveryAndArcSummaries:
    """Verify arc and recovery debug info propagates into the GM bundle."""

    def _build_bundle_with_arc_and_recovery(self) -> dict:
        core = DebugCore()
        return core.build_gm_inspection_bundle(
            tick=5,
            arc_debug_summary=_sample_arc_debug_summary(),
            recovery_debug_summary=_sample_recovery_debug_summary(),
        )

    def test_arc_summary_present(self) -> None:
        bundle = self._build_bundle_with_arc_and_recovery()
        arc = bundle.get("arc_summary", {})
        assert arc, "arc_summary should be present"
        assert arc.get("active_arc_count") == 1

    def test_arc_summary_has_pressure_fields(self) -> None:
        bundle = self._build_bundle_with_arc_and_recovery()
        arc = bundle.get("arc_summary", {})
        assert arc.get("reveal_pressure") == "high"
        assert arc.get("pacing_pressure") == "normal"

    def test_recovery_events_non_empty(self) -> None:
        bundle = self._build_bundle_with_arc_and_recovery()
        events = bundle.get("recovery_events", [])
        assert len(events) >= 1

    def test_warnings_include_recovery_warnings(self) -> None:
        bundle = self._build_bundle_with_arc_and_recovery()
        warnings = bundle.get("warnings", [])
        assert any("Contradiction" in w for w in warnings), (
            "recovery warning should propagate into bundle warnings"
        )


# ======================================================================
# 5. Debug build is read-only — no mutation of source data
# ======================================================================

class TestDebugBuildIsReadOnly:
    """Ensure that building debug payloads never mutates input dicts."""

    def test_choice_debug_does_not_mutate_control_output(self) -> None:
        control_output = {
            "choice_set": _sample_choice_set(),
            "pacing": {"tempo": "fast"},
        }
        original = copy.deepcopy(control_output)
        DebugCore().build_choice_debug_payload(control_output, tick=5)
        assert control_output == original

    def test_action_debug_does_not_mutate_action_result(self) -> None:
        action_result = {
            "resolved_action": {
                "action_id": "a1",
                "intent_type": "combat",
                "target_id": "goblin",
                "outcome": "hit",
                "summary": "Hit",
                "metadata": {},
            },
            "events": [{"event_type": "damage"}],
            "trace": {},
        }
        original = copy.deepcopy(action_result)
        DebugCore().build_action_debug_payload(action_result, tick=5)
        assert action_result == original

    def test_dialogue_explanation_does_not_mutate_inputs(self) -> None:
        response = _sample_dialogue_response()
        trace = _sample_dialogue_trace()
        resp_copy = copy.deepcopy(response)
        trace_copy = copy.deepcopy(trace)
        DebugTraceBuilder().build_dialogue_explanation(response, trace)
        assert response == resp_copy
        assert trace == trace_copy

    def test_encounter_explanation_does_not_mutate_inputs(self) -> None:
        state = _sample_encounter_state()
        resolution = _sample_encounter_resolution()
        state_copy = copy.deepcopy(state)
        res_copy = copy.deepcopy(resolution)
        DebugTraceBuilder().build_encounter_explanation(state, resolution)
        assert state == state_copy
        assert resolution == res_copy

    def test_world_explanation_does_not_mutate_inputs(self) -> None:
        result = _sample_world_sim_result()
        result_copy = copy.deepcopy(result)
        DebugTraceBuilder().build_world_sim_explanation(result)
        assert result == result_copy

    def test_gm_bundle_does_not_mutate_any_source(self) -> None:
        dialogue_response = _sample_dialogue_response()
        dialogue_trace = _sample_dialogue_trace()
        encounter_state = _sample_encounter_state()
        encounter_resolution = _sample_encounter_resolution()
        world_result = _sample_world_sim_result()

        all_copies = {
            "dialogue_response": copy.deepcopy(dialogue_response),
            "dialogue_trace": copy.deepcopy(dialogue_trace),
            "encounter_state": copy.deepcopy(encounter_state),
            "encounter_resolution": copy.deepcopy(encounter_resolution),
            "world_result": copy.deepcopy(world_result),
        }

        DebugCore().build_gm_inspection_bundle(
            tick=5,
            last_dialogue_response=dialogue_response,
            last_dialogue_trace=dialogue_trace,
            last_encounter_state=encounter_state,
            last_encounter_resolution=encounter_resolution,
            last_world_sim_result=world_result,
        )

        assert dialogue_response == all_copies["dialogue_response"]
        assert dialogue_trace == all_copies["dialogue_trace"]
        assert encounter_state == all_copies["encounter_state"]
        assert encounter_resolution == all_copies["encounter_resolution"]
        assert world_result == all_copies["world_result"]


# ======================================================================
# 6. UX presenter passes through debug
# ======================================================================

class TestUXPresenterPassesThroughDebug:
    """Verify the UX presenter includes the debug key when present."""

    def test_present_scene_payload_includes_debug(self) -> None:
        payload_dict = {
            "payload_id": "scene:5",
            "scene": {"location": "tavern"},
            "choices": [],
            "panels": [],
            "highlights": {},
            "debug": {"tick": 5, "choice_count": 2, "warning_count": 0},
        }
        presented = UXPresenter().present_scene_payload(payload_dict)
        assert "debug" in presented
        assert presented["debug"]["tick"] == 5
        assert presented["debug"]["choice_count"] == 2

    def test_present_action_result_payload_includes_debug(self) -> None:
        payload_dict = {
            "result_id": "r1",
            "action_result": {"choice_id": "opt_1"},
            "updated_scene": {},
            "updated_choices": [],
            "updated_panels": [],
            "debug": {"tick": 5, "warning_count": 1},
        }
        presented = UXPresenter().present_action_result_payload(payload_dict)
        assert "debug" in presented
        assert presented["debug"]["tick"] == 5
        assert presented["debug"]["warning_count"] == 1
