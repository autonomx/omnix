"""Comprehensive unit tests for Phase 8.4 — Debug / Analytics / GM Inspection.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_phase84_debug.py -v --noconftest
"""

from __future__ import annotations

import copy

import pytest

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
from app.rpg.debug.trace_builder import DebugTraceBuilder
from app.rpg.debug.presenter import DebugPresenter
from app.rpg.debug.core import DebugCore


# ======================================================================
# Helpers — reusable fixtures / factory data
# ======================================================================

def _make_option(**overrides) -> dict:
    """Build a minimal choice option dict."""
    opt: dict = {
        "option_id": "opt-1",
        "label": "Investigate rumour",
        "summary": "Look into the tavern rumour",
        "intent_type": "investigate",
        "target_id": "tavern",
        "tags": ["social"],
        "priority": 3.0,
        "selected": False,
        "metadata": {},
        "constraints": [],
    }
    opt.update(overrides)
    return opt


def _make_control_output(**overrides) -> dict:
    """Build a minimal control_output dict."""
    out: dict = {
        "choice_set": {
            "options": [_make_option()],
        },
    }
    out.update(overrides)
    return out


def _make_action_result(**overrides) -> dict:
    """Build a minimal action_result dict."""
    out: dict = {
        "resolved_action": {
            "action_id": "act-001",
            "intent_type": "investigate",
            "option_id": "opt-1",
            "target_id": "tavern",
            "outcome": "success",
            "summary": "Player investigates the tavern.",
            "metadata": {},
        },
        "events": [],
        "trace": {},
    }
    out.update(overrides)
    return out


def _make_dialogue_response(**overrides) -> dict:
    out: dict = {
        "speaker_id": "npc-barkeep",
        "listener_id": "player",
        "act": "inform",
        "tone": "friendly",
        "stance": "helpful",
        "summary": "The barkeep tells you about the missing merchant.",
    }
    out.update(overrides)
    return out


def _make_dialogue_trace(**overrides) -> dict:
    out: dict = {
        "decision_reasons": ["Trust is high", "Topic is relevant"],
        "state_drivers": {"trust": 0.8, "mood": "relaxed"},
        "primary_act": "inform",
        "secondary_acts": ["comfort"],
        "reveal_policy": {
            "blocked_topics": ["secret_identity"],
            "allowed_topics": ["quest_info", "rumors"],
        },
    }
    out.update(overrides)
    return out


def _make_encounter_state(**overrides) -> dict:
    out: dict = {
        "encounter_id": "enc-42",
        "mode": "negotiation",
        "pressure": 0.6,
        "stakes": "medium",
        "status": "active",
        "round_index": 2,
    }
    out.update(overrides)
    return out


def _make_encounter_trace(**overrides) -> dict:
    out: dict = {
        "outcome_type": "ongoing",
        "mode": "negotiation",
        "reasons": ["Pressure threshold not reached"],
        "participant_updates": [{"npc_id": "guard", "stance": "wary"}],
        "objective_updates": [{"objective_id": "obj-1", "progress": 0.5}],
        "state_updates": {"threat_level": "moderate"},
    }
    out.update(overrides)
    return out


def _make_world_result(**overrides) -> dict:
    out: dict = {
        "tick": 10,
        "advanced": True,
        "generated_effects": [
            {"effect_type": "thread_pressure_changed", "scope": "global", "target_id": "t-1"},
            {"effect_type": "rumor_spread", "scope": "local", "target_id": "r-1"},
            {"effect_type": "location_condition_changed", "scope": "local", "target_id": "loc-1"},
        ],
        "guidance": {"tension": "rising"},
    }
    out.update(overrides)
    return out


# ======================================================================
# 1. Constants
# ======================================================================

class TestConstants:
    """Verify constant sets have expected values."""

    def test_supported_debug_node_types(self):
        expected = {
            "choice_generation", "action_resolution", "dialogue_planning",
            "encounter_resolution", "world_sim_tick", "arc_guidance",
            "recovery_event", "pack_application",
        }
        assert SUPPORTED_DEBUG_NODE_TYPES == expected
        assert isinstance(SUPPORTED_DEBUG_NODE_TYPES, frozenset)
        assert len(SUPPORTED_DEBUG_NODE_TYPES) == 8

    def test_supported_debug_scopes(self):
        expected = {
            "choice", "action", "dialogue", "encounter", "world", "system",
        }
        assert SUPPORTED_DEBUG_SCOPES == expected
        assert isinstance(SUPPORTED_DEBUG_SCOPES, frozenset)
        assert len(SUPPORTED_DEBUG_SCOPES) == 6


# ======================================================================
# 2. Model roundtrips
# ======================================================================

class TestDebugTraceNodeRoundtrip:

    def test_full_roundtrip(self):
        node = DebugTraceNode(
            node_id="n1", node_type="choice_generation",
            title="Title", summary="Sum",
            inputs={"a": 1}, outputs={"b": 2},
            reasons=["r1"], metadata={"m": True},
        )
        d = node.to_dict()
        rebuilt = DebugTraceNode.from_dict(d)
        assert rebuilt.node_id == node.node_id
        assert rebuilt.reasons == node.reasons
        assert rebuilt.to_dict() == d

    def test_defaults_produce_valid_dict(self):
        node = DebugTraceNode(node_id="x", node_type="t", title="", summary="")
        d = node.to_dict()
        assert d["inputs"] == {}
        assert d["outputs"] == {}
        assert d["reasons"] == []
        assert d["metadata"] == {}

    def test_from_dict_with_empty_dict(self):
        node = DebugTraceNode.from_dict({})
        assert node.node_id == ""
        assert node.inputs == {}


class TestDebugTraceRoundtrip:

    def test_full_roundtrip(self):
        inner = DebugTraceNode(node_id="n1", node_type="t", title="T", summary="S")
        trace = DebugTrace(
            trace_id="tr-1", tick=5, scope="choice",
            nodes=[inner],
            warnings=["w1"],
            contradictions=[{"field": "x"}],
            metadata={"key": "val"},
        )
        d = trace.to_dict()
        rebuilt = DebugTrace.from_dict(d)
        assert rebuilt.trace_id == trace.trace_id
        assert rebuilt.tick == 5
        assert len(rebuilt.nodes) == 1
        assert rebuilt.nodes[0].node_id == "n1"
        assert rebuilt.to_dict() == d

    def test_defaults(self):
        trace = DebugTrace(trace_id="x")
        d = trace.to_dict()
        assert d["scope"] == "system"
        assert d["nodes"] == []
        assert d["tick"] is None

    def test_from_dict_empty(self):
        trace = DebugTrace.from_dict({})
        assert trace.trace_id == ""
        assert trace.scope == "system"
        assert trace.nodes == []


class TestChoiceExplanationRoundtrip:

    def test_full_roundtrip(self):
        ce = ChoiceExplanation(
            choice_id="c1", label="lbl", source="arc", priority="high",
            reasons=["r"], constraints=["con"], related_systems=["encounter"],
            metadata={"k": 1},
        )
        d = ce.to_dict()
        rebuilt = ChoiceExplanation.from_dict(d)
        assert rebuilt.to_dict() == d

    def test_defaults(self):
        ce = ChoiceExplanation(choice_id="c", label="l", source="s", priority="p")
        d = ce.to_dict()
        assert d["reasons"] == []
        assert d["constraints"] == []

    def test_from_dict_empty(self):
        ce = ChoiceExplanation.from_dict({})
        assert ce.choice_id == ""
        assert ce.reasons == []


class TestNPCResponseExplanationRoundtrip:

    def test_full_roundtrip(self):
        npc = NPCResponseExplanation(
            speaker_id="npc-1", listener_id="player",
            act="inform", tone="neutral", stance="guarded",
            drivers={"trust": 0.5}, reasons=["r1"],
            blocked_topics=["secret"], allowed_topics=["quest"],
            metadata={"reveal_policy": {}},
        )
        d = npc.to_dict()
        rebuilt = NPCResponseExplanation.from_dict(d)
        assert rebuilt.to_dict() == d

    def test_defaults(self):
        npc = NPCResponseExplanation(speaker_id="npc")
        d = npc.to_dict()
        assert d["listener_id"] is None
        assert d["act"] == ""
        assert d["blocked_topics"] == []

    def test_from_dict_empty(self):
        npc = NPCResponseExplanation.from_dict({})
        assert npc.speaker_id == ""
        assert npc.listener_id is None


class TestEncounterExplanationRoundtrip:

    def test_full_roundtrip(self):
        ee = EncounterExplanation(
            encounter_id="enc-1", mode="combat", outcome_type="victory",
            drivers={"pressure": 0.9}, reasons=["r"],
            participant_updates=[{"id": "p1"}],
            objective_updates=[{"id": "o1"}],
            metadata={"state_updates": {}},
        )
        d = ee.to_dict()
        rebuilt = EncounterExplanation.from_dict(d)
        assert rebuilt.to_dict() == d

    def test_defaults(self):
        ee = EncounterExplanation()
        d = ee.to_dict()
        assert d["encounter_id"] is None
        assert d["mode"] is None
        assert d["outcome_type"] == ""

    def test_from_dict_empty(self):
        ee = EncounterExplanation.from_dict({})
        assert ee.encounter_id is None


class TestWorldSimExplanationRoundtrip:

    def test_full_roundtrip(self):
        ws = WorldSimExplanation(
            sim_tick=7,
            effects=[{"effect_type": "x"}],
            pressure_changes=[{"target_id": "t"}],
            rumor_changes=[], location_changes=[],
            reasons=["r"], metadata={"advanced": True},
        )
        d = ws.to_dict()
        rebuilt = WorldSimExplanation.from_dict(d)
        assert rebuilt.to_dict() == d

    def test_defaults(self):
        ws = WorldSimExplanation()
        d = ws.to_dict()
        assert d["sim_tick"] == 0
        assert d["effects"] == []

    def test_from_dict_empty(self):
        ws = WorldSimExplanation.from_dict({})
        assert ws.sim_tick == 0


class TestGMInspectionBundleRoundtrip:

    def test_full_roundtrip(self):
        ce = ChoiceExplanation(choice_id="c1", label="l", source="s", priority="p")
        bundle = GMInspectionBundle(
            tick=3, scene={"location": "tavern"},
            choice_explanations=[ce],
            dialogue_explanation={"speaker_id": "npc"},
            encounter_explanation={"mode": "combat"},
            world_explanation={"sim_tick": 1},
            arc_explanation={"active_arcs": []},
            recovery_events=[{"type": "heal"}],
            warnings=["w1"],
            metadata={"packs": {}},
        )
        d = bundle.to_dict()
        rebuilt = GMInspectionBundle.from_dict(d)
        assert rebuilt.tick == 3
        assert len(rebuilt.choice_explanations) == 1
        assert rebuilt.choice_explanations[0].choice_id == "c1"
        assert rebuilt.to_dict() == d

    def test_defaults(self):
        bundle = GMInspectionBundle()
        d = bundle.to_dict()
        assert d["tick"] is None
        assert d["choice_explanations"] == []
        assert d["warnings"] == []

    def test_from_dict_empty(self):
        bundle = GMInspectionBundle.from_dict({})
        assert bundle.tick is None
        assert bundle.choice_explanations == []


# ======================================================================
# 3. Trace builder
# ======================================================================

class TestBuildChoiceTrace:

    def setup_method(self):
        self.builder = DebugTraceBuilder()

    def test_valid_control_output(self):
        ctrl = _make_control_output()
        trace = self.builder.build_choice_trace(ctrl, tick=1)
        assert isinstance(trace, DebugTrace)
        assert trace.scope == "choice"
        assert trace.tick == 1
        assert len(trace.nodes) == 1
        assert trace.nodes[0].node_type == "choice_generation"

    def test_empty_control_output(self):
        trace = self.builder.build_choice_trace({})
        assert trace.scope == "choice"
        assert trace.nodes == []

    def test_deterministic_structure(self):
        ctrl = _make_control_output()
        t1 = self.builder.build_choice_trace(ctrl, tick=5)
        t2 = self.builder.build_choice_trace(ctrl, tick=5)
        # Trace IDs differ (UUID), but structure matches
        assert t1.scope == t2.scope
        assert t1.tick == t2.tick
        assert len(t1.nodes) == len(t2.nodes)
        assert t1.nodes[0].title == t2.nodes[0].title

    def test_multiple_options(self):
        ctrl = _make_control_output(
            choice_set={"options": [_make_option(option_id="a"), _make_option(option_id="b")]},
        )
        trace = self.builder.build_choice_trace(ctrl)
        assert len(trace.nodes) == 2
        ids = {n.node_id for n in trace.nodes}
        assert "a" in ids and "b" in ids

    def test_pacing_framing_adds_context_node(self):
        ctrl = _make_control_output(pacing={"tempo": "slow"})
        trace = self.builder.build_choice_trace(ctrl)
        assert len(trace.nodes) == 2  # option + context
        ctx = trace.nodes[-1]
        assert ctx.title == "Control Context"
        assert "pacing" in ctx.inputs

    def test_external_bias_adds_context_node(self):
        ctrl = _make_control_output(external_bias={"bias": 0.1})
        trace = self.builder.build_choice_trace(ctrl)
        ctx = [n for n in trace.nodes if n.title == "Control Context"]
        assert len(ctx) == 1

    def test_no_context_node_without_pacing_framing_bias(self):
        ctrl = _make_control_output()
        trace = self.builder.build_choice_trace(ctrl)
        assert all(n.title != "Control Context" for n in trace.nodes)

    def test_option_metadata_filtering(self):
        opt = _make_option(metadata={
            "debug_source": "arc_system",
            "encounter_start": "enc-99",
            "source_system": "exploration",
            "irrelevant_key": "should_be_filtered",
        })
        ctrl = _make_control_output(choice_set={"options": [opt]})
        trace = self.builder.build_choice_trace(ctrl)
        meta = trace.nodes[0].metadata
        assert "debug_source" in meta
        assert "encounter_start" in meta
        assert "source_system" in meta
        assert "irrelevant_key" not in meta

    def test_option_inputs_populated(self):
        ctrl = _make_control_output()
        trace = self.builder.build_choice_trace(ctrl)
        inp = trace.nodes[0].inputs
        assert inp["intent_type"] == "investigate"
        assert inp["target_id"] == "tavern"
        assert inp["tags"] == ["social"]

    def test_option_outputs_populated(self):
        ctrl = _make_control_output()
        trace = self.builder.build_choice_trace(ctrl)
        out = trace.nodes[0].outputs
        assert out["priority"] == 3.0
        assert out["selected"] is False

    def test_trace_id_starts_with_choice(self):
        trace = self.builder.build_choice_trace(_make_control_output())
        assert trace.trace_id.startswith("choice-trace:")


class TestBuildActionTrace:

    def setup_method(self):
        self.builder = DebugTraceBuilder()

    def test_full_action_result(self):
        result = _make_action_result(
            events=[{"event_type": "damage"}, {"event_type": "damage"}, {"event_type": "dialogue"}],
        )
        result["resolved_action"]["metadata"] = {
            "dialogue_response": _make_dialogue_response(),
            "dialogue_trace": _make_dialogue_trace(),
            "encounter_id": "enc-42",
            "encounter_mode": "combat",
            "encounter_action_type": "attack",
            "mapped_action": "melee_strike",
        }
        trace = self.builder.build_action_trace(result, tick=2)
        assert trace.scope == "action"
        assert trace.tick == 2
        # Main node + dialogue + encounter + event summary = 4
        assert len(trace.nodes) == 4
        types = [n.node_type for n in trace.nodes]
        assert "action_resolution" in types
        assert "dialogue_planning" in types
        assert "encounter_resolution" in types

    def test_minimal_action_result(self):
        trace = self.builder.build_action_trace({})
        assert trace.scope == "action"
        assert len(trace.nodes) == 1  # just the main action node

    def test_preserves_event_counts(self):
        result = _make_action_result(events=[
            {"event_type": "damage"},
            {"event_type": "heal"},
            {"event_type": "damage"},
        ])
        trace = self.builder.build_action_trace(result)
        main_node = trace.nodes[0]
        assert main_node.outputs["event_count"] == 3

    def test_event_summary_node_created(self):
        result = _make_action_result(events=[
            {"event_type": "damage"},
            {"event_type": "damage"},
            {"event_type": "heal"},
        ])
        trace = self.builder.build_action_trace(result)
        evt_nodes = [n for n in trace.nodes if n.title == "Emitted Events"]
        assert len(evt_nodes) == 1
        counts = evt_nodes[0].outputs["event_type_counts"]
        assert counts["damage"] == 2
        assert counts["heal"] == 1

    def test_no_event_summary_without_events(self):
        result = _make_action_result(events=[])
        trace = self.builder.build_action_trace(result)
        assert all(n.title != "Emitted Events" for n in trace.nodes)

    def test_dialogue_node_not_created_without_dialogue(self):
        trace = self.builder.build_action_trace(_make_action_result())
        assert all(n.node_type != "dialogue_planning" for n in trace.nodes)

    def test_encounter_node_not_created_without_encounter(self):
        trace = self.builder.build_action_trace(_make_action_result())
        assert all(n.node_type != "encounter_resolution" for n in trace.nodes)

    def test_trace_id_starts_with_action(self):
        trace = self.builder.build_action_trace(_make_action_result())
        assert trace.trace_id.startswith("action-trace:")

    def test_main_node_reasons_with_mapped_action(self):
        result = _make_action_result()
        result["resolved_action"]["metadata"]["mapped_action"] = "talk"
        trace = self.builder.build_action_trace(result)
        reasons = trace.nodes[0].reasons
        assert any("Mapped action: talk" in r for r in reasons)

    def test_main_node_reasons_default(self):
        result = _make_action_result()
        result["resolved_action"]["outcome"] = ""
        result["resolved_action"]["metadata"] = {}
        result["trace"] = {}
        trace = self.builder.build_action_trace(result)
        reasons = trace.nodes[0].reasons
        assert "Action resolved via standard pipeline" in reasons


class TestBuildDialogueExplanation:

    def setup_method(self):
        self.builder = DebugTraceBuilder()

    def test_preserves_drivers_and_reasons(self):
        resp = _make_dialogue_response()
        trace = _make_dialogue_trace()
        expl = self.builder.build_dialogue_explanation(resp, trace)
        assert expl.speaker_id == "npc-barkeep"
        assert expl.listener_id == "player"
        assert expl.act == "inform"
        assert expl.drivers == {"trust": 0.8, "mood": "relaxed"}
        assert any("Trust is high" in r for r in expl.reasons)
        assert expl.blocked_topics == ["secret_identity"]
        assert expl.allowed_topics == ["quest_info", "rumors"]

    def test_missing_trace_data(self):
        resp = _make_dialogue_response(act="")
        expl = self.builder.build_dialogue_explanation(resp, {})
        assert "Dialogue reasons unavailable" in expl.reasons

    def test_fallback_to_act_from_response(self):
        resp = _make_dialogue_response(act="threaten")
        expl = self.builder.build_dialogue_explanation(resp, {})
        assert any("Act: threaten" in r for r in expl.reasons)

    def test_reveal_policy_suppressed_permitted_fallback(self):
        resp = _make_dialogue_response()
        trace = _make_dialogue_trace(reveal_policy={
            "suppressed": ["danger"],
            "permitted": ["lore"],
        })
        expl = self.builder.build_dialogue_explanation(resp, trace)
        assert expl.blocked_topics == ["danger"]
        assert expl.allowed_topics == ["lore"]

    def test_metadata_contains_reveal_policy(self):
        resp = _make_dialogue_response()
        trace = _make_dialogue_trace()
        expl = self.builder.build_dialogue_explanation(resp, trace)
        assert "reveal_policy" in expl.metadata

    def test_state_drivers_sorted_in_reasons(self):
        resp = _make_dialogue_response()
        trace = _make_dialogue_trace(state_drivers={"z_val": 1, "a_val": 2})
        expl = self.builder.build_dialogue_explanation(resp, trace)
        driver_reasons = [r for r in expl.reasons if ": " in r and r.split(":")[0] in ("a_val", "z_val")]
        assert len(driver_reasons) == 2
        assert driver_reasons[0].startswith("a_val")


class TestBuildEncounterExplanation:

    def setup_method(self):
        self.builder = DebugTraceBuilder()

    def test_preserves_updates_and_reasons(self):
        state = _make_encounter_state()
        trace = _make_encounter_trace()
        expl = self.builder.build_encounter_explanation(state, trace)
        assert expl.encounter_id == "enc-42"
        assert expl.mode == "negotiation"
        assert expl.outcome_type == "ongoing"
        assert len(expl.participant_updates) == 1
        assert len(expl.objective_updates) == 1
        assert any("Pressure threshold not reached" in r for r in expl.reasons)

    def test_empty_state(self):
        expl = self.builder.build_encounter_explanation({})
        assert expl.encounter_id is None
        assert expl.mode is None
        assert "Encounter reasons unavailable" in expl.reasons

    def test_mode_fallback_to_trace(self):
        expl = self.builder.build_encounter_explanation({}, {"mode": "stealth"})
        assert expl.mode == "stealth"

    def test_drivers_populated(self):
        state = _make_encounter_state()
        expl = self.builder.build_encounter_explanation(state)
        assert expl.drivers["pressure"] == 0.6
        assert expl.drivers["stakes"] == "medium"
        assert expl.drivers["round_index"] == 2

    def test_reason_string_handling(self):
        """Trace with 'reason' as a single string instead of 'reasons' list."""
        expl = self.builder.build_encounter_explanation({}, {"reason": "Timeout"})
        assert "Timeout" in expl.reasons


class TestBuildWorldSimExplanation:

    def setup_method(self):
        self.builder = DebugTraceBuilder()

    def test_groups_effect_types(self):
        result = _make_world_result()
        expl = self.builder.build_world_sim_explanation(result)
        assert expl.sim_tick == 10
        assert len(expl.pressure_changes) == 1
        assert len(expl.rumor_changes) == 1
        assert len(expl.location_changes) == 1
        assert len(expl.effects) == 3

    def test_empty_effects(self):
        result = _make_world_result(generated_effects=[], advanced=False)
        expl = self.builder.build_world_sim_explanation(result)
        assert expl.effects == []
        assert expl.pressure_changes == []
        assert any("did not advance" in r for r in expl.reasons)

    def test_advanced_flag_in_reasons(self):
        result = _make_world_result(advanced=True)
        expl = self.builder.build_world_sim_explanation(result)
        assert any("advanced" in r.lower() for r in expl.reasons)

    def test_metadata_contains_total_effect_count(self):
        result = _make_world_result()
        expl = self.builder.build_world_sim_explanation(result)
        assert expl.metadata["total_effect_count"] == 3
        assert expl.metadata["advanced"] is True

    def test_guidance_in_reasons(self):
        result = _make_world_result(guidance={"pacing": "fast", "tension": "high"})
        expl = self.builder.build_world_sim_explanation(result)
        assert any("Guidance pacing: fast" in r for r in expl.reasons)

    def test_effects_bounded_to_max(self):
        effects = [{"effect_type": f"type_{i}", "scope": "g", "target_id": f"t{i}"} for i in range(60)]
        result = _make_world_result(generated_effects=effects)
        expl = self.builder.build_world_sim_explanation(result)
        assert len(expl.effects) <= 50

    def test_rumor_cools_classified(self):
        result = _make_world_result(generated_effects=[
            {"effect_type": "rumor_cools", "scope": "local", "target_id": "r-2"},
        ])
        expl = self.builder.build_world_sim_explanation(result)
        assert len(expl.rumor_changes) == 1


class TestBuildGMBundle:

    def setup_method(self):
        self.builder = DebugTraceBuilder()

    def test_all_data_populated(self):
        bundle = self.builder.build_gm_bundle(
            tick=5,
            scene_payload={"location": "tavern"},
            control_output=_make_control_output(),
            last_dialogue_response=_make_dialogue_response(),
            last_dialogue_trace=_make_dialogue_trace(),
            last_encounter_state=_make_encounter_state(),
            last_encounter_resolution=_make_encounter_trace(),
            last_world_sim_result=_make_world_result(),
            arc_debug_summary={"active_arcs": ["a1"]},
            recovery_debug_summary={"recent_recoveries": [{"type": "heal"}], "warnings": ["w"]},
            pack_debug_summary={"pack_id": "p1"},
        )
        assert isinstance(bundle, GMInspectionBundle)
        assert bundle.tick == 5
        assert len(bundle.choice_explanations) == 1
        assert bundle.dialogue_explanation != {}
        assert bundle.encounter_explanation != {}
        assert bundle.world_explanation != {}
        assert bundle.arc_explanation != {}
        assert len(bundle.recovery_events) == 1
        assert "w" in bundle.warnings
        assert bundle.metadata.get("packs", {}).get("pack_id") == "p1"

    def test_all_none_inputs(self):
        bundle = self.builder.build_gm_bundle()
        assert bundle.tick is None
        assert bundle.choice_explanations == []
        assert bundle.dialogue_explanation == {}
        assert bundle.encounter_explanation == {}
        assert bundle.world_explanation == {}
        assert bundle.arc_explanation == {}
        assert bundle.recovery_events == []
        assert bundle.warnings == []

    def test_partial_data(self):
        bundle = self.builder.build_gm_bundle(
            tick=1,
            control_output=_make_control_output(),
        )
        assert bundle.tick == 1
        assert len(bundle.choice_explanations) == 1
        assert bundle.dialogue_explanation == {}

    def test_choice_constraints_extracted(self):
        opt = _make_option(constraints=[
            {"constraint_type": "reputation_min"},
            "simple_string_constraint",
        ])
        ctrl = _make_control_output(choice_set={"options": [opt]})
        bundle = self.builder.build_gm_bundle(control_output=ctrl)
        constraints = bundle.choice_explanations[0].constraints
        assert "reputation_min" in constraints
        assert "simple_string_constraint" in constraints

    def test_choice_related_systems(self):
        opt = _make_option(metadata={
            "encounter_start": "enc-10",
            "debug_source": "faction_system",
        })
        ctrl = _make_control_output(choice_set={"options": [opt]})
        bundle = self.builder.build_gm_bundle(control_output=ctrl)
        related = bundle.choice_explanations[0].related_systems
        assert "encounter" in related
        assert "faction_system" in related

    def test_choice_source_from_metadata(self):
        opt = _make_option(metadata={"debug_source": "arc_engine"})
        ctrl = _make_control_output(choice_set={"options": [opt]})
        bundle = self.builder.build_gm_bundle(control_output=ctrl)
        assert bundle.choice_explanations[0].source == "arc_engine"

    def test_choice_source_default_standard(self):
        ctrl = _make_control_output()
        bundle = self.builder.build_gm_bundle(control_output=ctrl)
        assert bundle.choice_explanations[0].source == "standard"


class TestNormalizeWarningList:

    def test_deduplicates(self):
        result = DebugTraceBuilder._normalize_warning_list(
            ["a", "b", "a", "c", "b"]
        )
        assert result == ["a", "b", "c"]

    def test_bounds_at_30(self):
        warnings = [f"w-{i}" for i in range(50)]
        result = DebugTraceBuilder._normalize_warning_list(warnings)
        assert len(result) == 30

    def test_empty_input(self):
        assert DebugTraceBuilder._normalize_warning_list([]) == []

    def test_preserves_order(self):
        result = DebugTraceBuilder._normalize_warning_list(["z", "a", "m"])
        assert result == ["z", "a", "m"]


class TestExtractChoiceReasons:

    def test_default_reason_when_no_metadata(self):
        reasons = DebugTraceBuilder._extract_choice_reasons({})
        assert reasons == ["Standard option generation"]

    def test_debug_reasons_extracted(self):
        opt = {"metadata": {"debug_reasons": ["r1", "r2"]}}
        reasons = DebugTraceBuilder._extract_choice_reasons(opt)
        assert "r1" in reasons
        assert "r2" in reasons

    def test_priority_in_reasons(self):
        opt = {"priority": 5.0}
        reasons = DebugTraceBuilder._extract_choice_reasons(opt)
        assert any("Priority: 5.0" in r for r in reasons)

    def test_constraints_count_in_reasons(self):
        opt = {"constraints": [{"type": "a"}, {"type": "b"}]}
        reasons = DebugTraceBuilder._extract_choice_reasons(opt)
        assert any("Constraints: 2 applied" in r for r in reasons)

    def test_bounded_to_max_reasons(self):
        opt = {"metadata": {"debug_reasons": [f"r{i}" for i in range(25)]}}
        reasons = DebugTraceBuilder._extract_choice_reasons(opt)
        assert len(reasons) <= 20


class TestExtractExecutionReasons:

    def test_mapped_action(self):
        resolved = {"metadata": {"mapped_action": "dodge"}}
        reasons = DebugTraceBuilder._extract_execution_reasons(resolved, {})
        assert any("Mapped action: dodge" in r for r in reasons)

    def test_evaluation_dict(self):
        resolved = {"metadata": {"evaluation": {"outcome": "partial_success"}}}
        reasons = DebugTraceBuilder._extract_execution_reasons(resolved, {})
        assert any("Evaluation outcome: partial_success" in r for r in reasons)

    def test_evaluation_string(self):
        resolved = {"metadata": {"evaluation": "auto_pass"}}
        reasons = DebugTraceBuilder._extract_execution_reasons(resolved, {})
        assert any("Evaluation: auto_pass" in r for r in reasons)

    def test_constraint_check_failed(self):
        resolved = {"metadata": {"constraint_evaluation": {"valid": False}}}
        reasons = DebugTraceBuilder._extract_execution_reasons(resolved, {})
        assert "Constraint check failed" in reasons

    def test_trace_decision_reasons(self):
        resolved = {"metadata": {}}
        trace = {"decision_reasons": ["decided via AI"]}
        reasons = DebugTraceBuilder._extract_execution_reasons(resolved, trace)
        assert "decided via AI" in reasons

    def test_default_reason(self):
        reasons = DebugTraceBuilder._extract_execution_reasons({"metadata": {}}, {})
        assert "Action resolved via standard pipeline" in reasons


# ======================================================================
# 4. Presenter
# ======================================================================

class TestPresenter:

    def setup_method(self):
        self.presenter = DebugPresenter()

    # present_trace ---------------------------------------------------

    def test_present_trace_compact(self):
        node = DebugTraceNode(
            node_id="n1", node_type="choice_generation",
            title="T", summary="S", reasons=["r1"],
        )
        trace = DebugTrace(trace_id="tr-1", tick=1, scope="choice", nodes=[node])
        result = self.presenter.present_trace(trace)
        assert result["trace_id"] == "tr-1"
        assert result["node_count"] == 1
        assert result["nodes"][0]["node_id"] == "n1"

    def test_present_trace_none(self):
        assert self.presenter.present_trace(None) == {}

    def test_present_trace_dict_input(self):
        data = {
            "trace_id": "x",
            "tick": 2,
            "scope": "action",
            "nodes": [{"node_id": "n", "node_type": "t", "title": "T", "summary": "S"}],
            "warnings": [],
        }
        result = self.presenter.present_trace(data)
        assert result["trace_id"] == "x"
        assert result["node_count"] == 1

    def test_present_trace_warnings_bounded(self):
        trace = DebugTrace(
            trace_id="t", warnings=[f"w{i}" for i in range(20)],
        )
        result = self.presenter.present_trace(trace)
        assert len(result["warnings"]) <= 15

    # present_choice_explanations ------------------------------------

    def test_present_choice_explanations(self):
        ce = ChoiceExplanation(
            choice_id="c1", label="l", source="s", priority="p",
            reasons=["r"], constraints=["con"],
        )
        result = self.presenter.present_choice_explanations([ce])
        assert len(result) == 1
        assert result[0]["choice_id"] == "c1"
        assert "constraints" in result[0]

    def test_present_choice_explanations_bounded(self):
        clist = [
            ChoiceExplanation(choice_id=f"c{i}", label="", source="", priority="")
            for i in range(25)
        ]
        result = self.presenter.present_choice_explanations(clist)
        assert len(result) <= 20

    def test_present_choice_explanations_dict_input(self):
        result = self.presenter.present_choice_explanations([
            {"choice_id": "x", "label": "l", "source": "s", "priority": "p"},
        ])
        assert result[0]["choice_id"] == "x"

    # present_gm_bundle ----------------------------------------------

    def test_present_gm_bundle_compact(self):
        builder = DebugTraceBuilder()
        bundle = builder.build_gm_bundle(
            tick=5,
            scene_payload={"location": "tavern", "active_threads": 3},
            control_output=_make_control_output(),
            last_dialogue_response=_make_dialogue_response(),
            last_dialogue_trace=_make_dialogue_trace(),
            last_encounter_state=_make_encounter_state(),
            last_encounter_resolution=_make_encounter_trace(),
            last_world_sim_result=_make_world_result(),
            arc_debug_summary={"active_arcs": ["a1"], "reveal_pressure": "high", "pacing_pressure": "low"},
        )
        result = self.presenter.present_gm_bundle(bundle)
        assert result["tick"] == 5
        assert result["scene_summary"]["location"] == "tavern"
        assert result["scene_summary"]["active_threads"] == 3
        assert len(result["choices"]) == 1
        assert result["dialogue_summary"]["speaker_id"] == "npc-barkeep"
        assert result["encounter_summary"]["encounter_id"] == "enc-42"
        assert result["world_summary"]["sim_tick"] == 10
        assert result["arc_summary"]["active_arc_count"] == 1

    def test_present_gm_bundle_none(self):
        assert self.presenter.present_gm_bundle(None) == {}

    def test_present_gm_bundle_dict_input(self):
        data = {
            "tick": 1,
            "scene": {},
            "choice_explanations": [],
            "dialogue_explanation": {},
            "encounter_explanation": {},
            "world_explanation": {},
            "arc_explanation": {},
            "recovery_events": [],
            "warnings": [],
        }
        result = self.presenter.present_gm_bundle(data)
        assert result["tick"] == 1

    def test_present_gm_bundle_recovery_events_bounded(self):
        data = GMInspectionBundle(
            recovery_events=[{"type": f"r{i}"} for i in range(15)],
        )
        result = self.presenter.present_gm_bundle(data)
        assert len(result["recovery_events"]) <= 10

    def test_present_gm_bundle_warnings_bounded(self):
        data = GMInspectionBundle(
            warnings=[f"w{i}" for i in range(20)],
        )
        result = self.presenter.present_gm_bundle(data)
        assert len(result["warnings"]) <= 15

    def test_present_gm_bundle_dialogue_reasons_capped(self):
        bundle = GMInspectionBundle(
            dialogue_explanation={
                "speaker_id": "npc",
                "act": "a",
                "tone": "t",
                "stance": "s",
                "reasons": [f"r{i}" for i in range(20)],
            },
        )
        result = self.presenter.present_gm_bundle(bundle)
        assert len(result["dialogue_summary"]["reasons"]) <= 5

    # present_system_summary -----------------------------------------

    def test_present_system_summary(self):
        result = self.presenter.present_system_summary(
            tick=3, choice_count=4, has_dialogue=True,
            has_encounter=False, world_effect_count=7,
            warning_count=2, arc_summary={"key": "val"},
        )
        assert result["tick"] == 3
        assert result["choice_count"] == 4
        assert result["has_dialogue"] is True
        assert result["has_encounter"] is False
        assert result["world_effect_count"] == 7
        assert result["warning_count"] == 2
        assert result["arc_summary"] == {"key": "val"}

    def test_present_system_summary_defaults(self):
        result = self.presenter.present_system_summary()
        assert result["tick"] is None
        assert result["choice_count"] == 0
        assert result["arc_summary"] == {}

    # No mutation ----------------------------------------------------

    def test_present_trace_no_mutation(self):
        node = DebugTraceNode(
            node_id="n1", node_type="t", title="T", summary="S",
            reasons=["r"],
        )
        trace = DebugTrace(trace_id="tr-1", nodes=[node], warnings=["w"])
        original = trace.to_dict()
        self.presenter.present_trace(trace)
        assert trace.to_dict() == original

    def test_present_gm_bundle_no_mutation(self):
        bundle = GMInspectionBundle(
            tick=1,
            warnings=["w1", "w2"],
            recovery_events=[{"a": 1}],
        )
        original = bundle.to_dict()
        self.presenter.present_gm_bundle(bundle)
        assert bundle.to_dict() == original


# ======================================================================
# 5. Core (DebugCore)
# ======================================================================

class TestDebugCore:

    def setup_method(self):
        self.core = DebugCore()

    def test_build_choice_debug_payload_returns_dict(self):
        result = self.core.build_choice_debug_payload(_make_control_output(), tick=1)
        assert isinstance(result, dict)
        assert "trace_id" in result
        assert "node_count" in result

    def test_build_action_debug_payload_returns_dict(self):
        result = self.core.build_action_debug_payload(_make_action_result(), tick=2)
        assert isinstance(result, dict)
        assert "trace_id" in result

    def test_build_gm_inspection_bundle_returns_dict(self):
        result = self.core.build_gm_inspection_bundle(
            tick=3,
            scene_payload={"location": "forest"},
            control_output=_make_control_output(),
        )
        assert isinstance(result, dict)
        expected_keys = {
            "tick", "scene_summary", "choices", "dialogue_summary",
            "encounter_summary", "world_summary", "arc_summary",
            "recovery_events", "warnings",
        }
        assert expected_keys.issubset(result.keys())

    def test_build_gm_inspection_bundle_all_none(self):
        result = self.core.build_gm_inspection_bundle()
        assert result["choices"] == []
        assert result["dialogue_summary"] == {}
        assert result["encounter_summary"] == {}
        assert result["world_summary"] == {}

    def test_build_system_debug_snapshot_shape(self):
        result = self.core.build_system_debug_snapshot(
            tick=10,
            control_output=_make_control_output(),
            last_dialogue_response=_make_dialogue_response(),
            has_encounter=True,
            world_effect_count=5,
            warning_count=1,
            arc_summary={"arcs": 2},
        )
        assert result["tick"] == 10
        assert result["choice_count"] == 1
        assert result["has_dialogue"] is True
        assert result["has_encounter"] is True
        assert result["world_effect_count"] == 5
        assert result["warning_count"] == 1
        assert result["arc_summary"] == {"arcs": 2}

    def test_build_system_debug_snapshot_defaults(self):
        result = self.core.build_system_debug_snapshot()
        assert result["tick"] is None
        assert result["choice_count"] == 0
        assert result["has_dialogue"] is False
        assert result["has_encounter"] is False

    def test_build_system_debug_snapshot_choice_count_from_control(self):
        ctrl = {
            "choice_set": {
                "options": [_make_option(option_id="a"), _make_option(option_id="b")],
            },
        }
        result = self.core.build_system_debug_snapshot(control_output=ctrl)
        assert result["choice_count"] == 2

    def test_stateless_no_side_effects(self):
        """Calling one method should not affect another."""
        core = DebugCore()
        r1 = core.build_choice_debug_payload(_make_control_output(), tick=1)
        r2 = core.build_action_debug_payload(_make_action_result(), tick=2)
        r3 = core.build_choice_debug_payload(_make_control_output(), tick=3)
        assert r1["scope"] == "choice"
        assert r2["scope"] == "action"
        assert r3["scope"] == "choice"
        assert r1["tick"] == 1
        assert r3["tick"] == 3

    def test_empty_control_output_choice_payload(self):
        result = self.core.build_choice_debug_payload({})
        assert result["node_count"] == 0
        assert result["nodes"] == []

    def test_gm_bundle_with_recovery_warnings(self):
        result = self.core.build_gm_inspection_bundle(
            recovery_debug_summary={
                "recent_recoveries": [{"event": "auto_heal"}],
                "warnings": ["state corruption detected"],
            },
        )
        assert len(result["recovery_events"]) >= 1
        assert any("state corruption detected" in w for w in result["warnings"])

    def test_gm_bundle_with_full_data(self):
        result = self.core.build_gm_inspection_bundle(
            tick=7,
            scene_payload={"location": "castle", "active_threads": 2},
            control_output=_make_control_output(),
            last_dialogue_response=_make_dialogue_response(),
            last_dialogue_trace=_make_dialogue_trace(),
            last_encounter_state=_make_encounter_state(),
            last_encounter_resolution=_make_encounter_trace(),
            last_world_sim_result=_make_world_result(),
            arc_debug_summary={"active_arcs": ["main_quest"], "reveal_pressure": "med", "pacing_pressure": "low"},
            recovery_debug_summary={"recent_recoveries": [], "warnings": []},
            pack_debug_summary={"pack_id": "core"},
        )
        assert result["tick"] == 7
        assert result["scene_summary"]["location"] == "castle"
        assert len(result["choices"]) == 1
        assert result["dialogue_summary"]["speaker_id"] == "npc-barkeep"
        assert result["encounter_summary"]["encounter_id"] == "enc-42"
        assert result["world_summary"]["sim_tick"] == 10
        assert result["arc_summary"]["active_arc_count"] == 1
