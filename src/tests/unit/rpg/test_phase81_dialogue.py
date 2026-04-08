"""Phase 8.1 — Dialogue Unit Tests.

Covers pure logic: act mapping, tone/stance shaping, context building,
planner determinism, and presenter output.
"""

from __future__ import annotations

import copy
import os
import sys

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.dialogue.acts import (
    SUPPORTED_DIALOGUE_ACTS,
    map_arc_pressure_to_reveal_level,
    map_npc_outcome_to_primary_act,
    map_relationship_to_stance,
    map_relationship_to_tone,
    map_scene_bias_to_dialogue_tags,
    normalize_dialogue_act,
)
from app.rpg.dialogue.context_builder import DialogueContextBuilder
from app.rpg.dialogue.core import DialogueCore
from app.rpg.dialogue.models import (
    DialogueActDecision,
    DialogueLogEntry,
    DialoguePresentation,
    DialogueResponsePlan,
    DialogueTurnContext,
)
from app.rpg.dialogue.presenter import DialoguePresenter
from app.rpg.dialogue.response_planner import DialogueResponsePlanner

# ======================================================================
# Act mapping tests
# ======================================================================

class TestMapNpcOutcomeToPrimaryAct:
    """map_npc_outcome_to_primary_act pure mapping tests."""

    def test_agree_maps_to_agreement(self):
        assert map_npc_outcome_to_primary_act("agree") == "agreement"

    def test_assist_maps_to_agreement(self):
        assert map_npc_outcome_to_primary_act("assist") == "agreement"

    def test_refuse_maps_to_refusal(self):
        assert map_npc_outcome_to_primary_act("refuse") == "refusal"

    def test_threaten_maps_to_threat(self):
        assert map_npc_outcome_to_primary_act("threaten") == "threat"

    def test_redirect_maps_to_redirect(self):
        assert map_npc_outcome_to_primary_act("redirect") == "redirect"

    def test_delay_maps_to_stall(self):
        assert map_npc_outcome_to_primary_act("delay") == "stall"

    def test_suspicious_maps_to_probe(self):
        assert map_npc_outcome_to_primary_act("suspicious") == "probe"

    def test_unknown_outcome_maps_to_acknowledge(self):
        assert map_npc_outcome_to_primary_act("unknown") == "acknowledge"

    def test_empty_outcome_maps_to_acknowledge(self):
        assert map_npc_outcome_to_primary_act("") == "acknowledge"

    def test_warn_maps_to_warn(self):
        assert map_npc_outcome_to_primary_act("warn") == "warn"

    def test_offer_maps_to_offer(self):
        assert map_npc_outcome_to_primary_act("offer") == "offer"

    def test_reveal_maps_to_reveal_hint(self):
        assert map_npc_outcome_to_primary_act("reveal") == "reveal_hint"


class TestMapRelationshipToTone:
    """map_relationship_to_tone deterministic tests."""

    def test_high_hostility_hostile(self):
        assert map_relationship_to_tone({"hostility": 0.8}) == "hostile"

    def test_high_fear_fearful(self):
        assert map_relationship_to_tone({"fear": 0.7}) == "fearful"

    def test_high_trust_warm(self):
        assert map_relationship_to_tone({"trust": 0.9}) == "warm"

    def test_high_respect_formal(self):
        assert map_relationship_to_tone({"respect": 0.7}) == "formal"

    def test_neutral_fallback(self):
        assert map_relationship_to_tone({}) == "neutral"

    def test_hostility_takes_priority_over_trust(self):
        assert map_relationship_to_tone({"hostility": 0.7, "trust": 0.9}) == "hostile"

    def test_fear_takes_priority_over_trust(self):
        assert map_relationship_to_tone({"fear": 0.7, "trust": 0.9}) == "fearful"


class TestMapRelationshipToStance:
    """map_relationship_to_stance deterministic tests."""

    def test_high_hostility_high_fear_defensive(self):
        assert map_relationship_to_stance({"hostility": 0.7, "fear": 0.7}) == "defensive"

    def test_high_hostility_aggressive(self):
        assert map_relationship_to_stance({"hostility": 0.8, "fear": 0.2}) == "aggressive"

    def test_high_trust_low_hostility_cooperative(self):
        assert map_relationship_to_stance({"trust": 0.8, "hostility": 0.1}) == "cooperative"

    def test_high_fear_only_defensive(self):
        assert map_relationship_to_stance({"fear": 0.8}) == "defensive"

    def test_neutral_fallback(self):
        assert map_relationship_to_stance({}) == "neutral"

    def test_no_known_relationship_neutral(self):
        assert map_relationship_to_stance({"trust": 0.0, "hostility": 0.0, "fear": 0.0}) == "neutral"


class TestMapArcPressureToRevealLevel:
    """map_arc_pressure_to_reveal_level deterministic tests."""

    def test_due_reveals_high(self):
        assert map_arc_pressure_to_reveal_level({"due_reveals": [{"reveal_id": "r1"}]}) == "high"

    def test_revelatory_scene_high(self):
        ctx = {"due_reveals": [], "active_scene_bias": {"scene_type_bias": "revelatory"}}
        assert map_arc_pressure_to_reveal_level(ctx) == "high"

    def test_tense_scene_medium(self):
        ctx = {"due_reveals": [], "active_scene_bias": {"scene_type_bias": "tense"}}
        assert map_arc_pressure_to_reveal_level(ctx) == "medium"

    def test_fast_tempo_medium(self):
        ctx = {"due_reveals": [], "active_pacing_plan": {"tempo": "fast"}, "active_scene_bias": {}}
        assert map_arc_pressure_to_reveal_level(ctx) == "medium"

    def test_slow_tempo_low(self):
        ctx = {"due_reveals": [], "active_pacing_plan": {"tempo": "slow"}, "active_scene_bias": {}}
        assert map_arc_pressure_to_reveal_level(ctx) == "low"

    def test_no_pressure_none(self):
        assert map_arc_pressure_to_reveal_level({}) == "none"


class TestMapSceneBiasToDialogueTags:
    """map_scene_bias_to_dialogue_tags deterministic tests."""

    def test_tense_bias(self):
        assert "tense" in map_scene_bias_to_dialogue_tags({"scene_type_bias": "tense"})

    def test_urgent_bias(self):
        assert "urgent" in map_scene_bias_to_dialogue_tags({"scene_type_bias": "urgent"})

    def test_framed_bias(self):
        assert "framed" in map_scene_bias_to_dialogue_tags({"force_option_framing": True})

    def test_empty_bias(self):
        assert map_scene_bias_to_dialogue_tags({}) == []


class TestNormalizeDialogueAct:
    """normalize_dialogue_act tests."""

    def test_valid_act_passes_through(self):
        assert normalize_dialogue_act("threat") == "threat"

    def test_unknown_act_falls_back(self):
        assert normalize_dialogue_act("yell") == "acknowledge"

    def test_whitespace_stripped(self):
        assert normalize_dialogue_act("  refusal  ") == "refusal"

    def test_case_insensitive(self):
        assert normalize_dialogue_act("THREAT") == "threat"

    def test_all_supported_acts_are_valid(self):
        for act in SUPPORTED_DIALOGUE_ACTS:
            assert normalize_dialogue_act(act) == act


# ======================================================================
# Model tests
# ======================================================================

class TestDialogueTurnContextModel:
    """DialogueTurnContext serialization tests."""

    def test_to_dict_from_dict_roundtrip(self):
        ctx = DialogueTurnContext(
            speaker_id="npc_a",
            listener_id="player",
            scene_location="tavern",
            current_intent_type="talk_to_npc",
            current_action_outcome="agree",
            current_tags=["social_contact"],
        )
        d = ctx.to_dict()
        ctx2 = DialogueTurnContext.from_dict(d)
        assert ctx2.to_dict() == d

    def test_default_values(self):
        ctx = DialogueTurnContext(speaker_id="x")
        assert ctx.listener_id is None
        assert ctx.interaction_history == []
        assert ctx.current_tags == []


class TestDialogueResponsePlanModel:
    """DialogueResponsePlan serialization tests."""

    def test_to_dict_from_dict_roundtrip(self):
        plan = DialogueResponsePlan(
            response_id="test",
            speaker_id="npc",
            primary_act="refusal",
            text_slots={"line": "No.", "summary": "Refused"},
        )
        d = plan.to_dict()
        plan2 = DialogueResponsePlan.from_dict(d)
        assert plan2.to_dict() == d


class TestDialoguePresentationModel:
    """DialoguePresentation serialization tests."""

    def test_to_dict_from_dict_roundtrip(self):
        pres = DialoguePresentation(
            speaker_id="npc",
            act="threat",
            tone="hostile",
            line="Leave now.",
        )
        d = pres.to_dict()
        pres2 = DialoguePresentation.from_dict(d)
        assert pres2.to_dict() == d


class TestDialogueLogEntryModel:
    """DialogueLogEntry serialization tests."""

    def test_to_dict_from_dict_roundtrip(self):
        entry = DialogueLogEntry(
            entry_id="e1",
            tick=5,
            speaker_id="npc",
            act="refusal",
            outcome="hostile",
            summary="NPC refused.",
            line="No.",
        )
        d = entry.to_dict()
        entry2 = DialogueLogEntry.from_dict(d)
        assert entry2.to_dict() == d


class TestDialogueActDecisionModel:
    """DialogueActDecision serialization tests."""

    def test_to_dict_from_dict_roundtrip(self):
        dec = DialogueActDecision(
            primary_act="threat",
            tone="hostile",
            stance="aggressive",
        )
        d = dec.to_dict()
        dec2 = DialogueActDecision.from_dict(d)
        assert dec2.to_dict() == d


# ======================================================================
# Context builder tests
# ======================================================================

class TestDialogueContextBuilder:
    """DialogueContextBuilder deterministic extraction tests."""

    def test_missing_npc_data_gives_sparse_defaults(self):
        builder = DialogueContextBuilder()
        ctx = builder.build_for_interaction(speaker_id="unknown_npc")
        assert ctx.speaker_state["known"] is False
        assert ctx.speaker_state["role"] == "unknown"

    def test_scene_summary_passthrough(self):
        builder = DialogueContextBuilder()
        scene = {"location": "market", "summary": "Busy day"}
        ctx = builder.build_for_interaction(
            speaker_id="npc",
            scene_summary=scene,
        )
        assert ctx.scene_location == "market"
        assert ctx.scene_summary["summary"] == "Busy day"

    def test_npc_decision_overrides_outcome(self):
        builder = DialogueContextBuilder()
        ctx = builder.build_for_interaction(
            speaker_id="npc",
            npc_decision={"outcome": "refuse", "response_type": "hostile"},
        )
        assert ctx.current_action_outcome == "refuse"
        assert "hostile" in ctx.current_tags

    def test_interaction_history_is_bounded(self):
        """History should be capped at 5 entries."""
        builder = DialogueContextBuilder()

        class _MockMemory:
            class _Entry:
                def __init__(self, entry_id, entity_ids):
                    self.entry_id = entry_id
                    self.entity_ids = entity_ids
                def to_dict(self):
                    return {"entry_id": self.entry_id, "entity_ids": self.entity_ids}

            def __init__(self):
                self.journal_entries = [
                    self._Entry(f"e{i}", ["npc"]) for i in range(20)
                ]

        ctx = builder.build_for_interaction(
            speaker_id="npc",
            history_source=_MockMemory(),
        )
        assert len(ctx.interaction_history) <= 5

    def test_same_input_produces_same_output(self):
        builder = DialogueContextBuilder()
        args = dict(
            speaker_id="npc_a",
            listener_id="player",
            scene_summary={"location": "cave"},
        )
        ctx1 = builder.build_for_interaction(**args)
        ctx2 = builder.build_for_interaction(**args)
        assert ctx1.to_dict() == ctx2.to_dict()

    def test_state_drivers_normalized(self):
        builder = DialogueContextBuilder()
        ctx = builder.build_for_interaction(speaker_id="npc")
        drivers = ctx.metadata.get("state_drivers", {})
        assert "openness" in drivers
        assert "hostility" in drivers
        assert "trust" in drivers
        assert "fear" in drivers
        assert "respect" in drivers
        assert "reveal_pressure" in drivers
        assert "scene_tension" in drivers


# ======================================================================
# Response planner tests
# ======================================================================

class TestDialogueResponsePlanner:
    """DialogueResponsePlanner classification and plan building tests."""

    def _make_context(self, **overrides) -> DialogueTurnContext:
        defaults = {
            "speaker_id": "npc",
            "listener_id": "player",
            "metadata": {"state_drivers": {
                "openness": "medium", "hostility": "low", "trust": "medium",
                "fear": "low", "respect": "medium", "reveal_pressure": "none",
                "scene_tension": "low", "urgency": "normal", "interaction_mode": "social",
            }},
        }
        defaults.update(overrides)
        return DialogueTurnContext(**defaults)

    def test_refused_outcome_gives_refusal(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_action_outcome="refuse")
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "refusal"

    def test_threaten_outcome_gives_threat(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_action_outcome="threaten")
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "threat"

    def test_high_hostility_gives_threat(self):
        planner = DialogueResponsePlanner()
        drivers = {
            "openness": "low", "hostility": "high", "trust": "low",
            "fear": "low", "respect": "low", "reveal_pressure": "none",
            "scene_tension": "low", "urgency": "normal", "interaction_mode": "social",
        }
        ctx = self._make_context(metadata={"state_drivers": drivers})
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "threat"

    def test_redirect_outcome_gives_redirect(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_action_outcome="redirect")
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "redirect"

    def test_agree_outcome_gives_agreement(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_action_outcome="agree")
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "agreement"

    def test_reveal_pressure_cooperative_gives_reveal_hint(self):
        planner = DialogueResponsePlanner()
        drivers = {
            "openness": "high", "hostility": "low", "trust": "high",
            "fear": "low", "respect": "medium", "reveal_pressure": "high",
            "scene_tension": "low", "urgency": "normal", "interaction_mode": "social",
        }
        ctx = self._make_context(
            metadata={"state_drivers": drivers},
            arc_context={"due_reveals": [{"reveal_id": "r1"}]},
        )
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "reveal_hint"

    def test_question_intent_gives_probe(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_intent_type="question")
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "probe"

    def test_default_gives_acknowledge(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context()
        dec = planner.classify_act(ctx)
        assert dec.primary_act == "acknowledge"

    def test_build_plan_deterministic(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_action_outcome="refuse")
        plan1 = planner.build_plan(ctx)
        plan2 = planner.build_plan(ctx)
        assert plan1.to_dict() == plan2.to_dict()

    def test_plan_has_text_slots(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_action_outcome="refuse")
        plan = planner.build_plan(ctx)
        assert "line" in plan.text_slots
        assert "summary" in plan.text_slots

    def test_plan_trace_shows_selected_act(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(current_action_outcome="threaten")
        plan = planner.build_plan(ctx)
        assert plan.trace["selected_act"] == "threat"

    def test_all_emitted_acts_are_supported(self):
        planner = DialogueResponsePlanner()
        for outcome in ["agree", "refuse", "threaten", "redirect", "delay", "offer", ""]:
            ctx = self._make_context(current_action_outcome=outcome)
            dec = planner.classify_act(ctx)
            assert dec.primary_act in SUPPORTED_DIALOGUE_ACTS

    def test_tone_from_relationship(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(
            relationship_state={"trust": 0.9, "hostility": 0.0, "fear": 0.0, "respect": 0.0},
        )
        dec = planner.classify_act(ctx)
        assert dec.tone == "warm"

    def test_stance_from_relationship(self):
        planner = DialogueResponsePlanner()
        ctx = self._make_context(
            relationship_state={"trust": 0.0, "hostility": 0.8, "fear": 0.8, "respect": 0.0},
        )
        dec = planner.classify_act(ctx)
        assert dec.stance == "defensive"


# ======================================================================
# Presenter tests
# ======================================================================

class TestDialoguePresenter:
    """DialoguePresenter output tests."""

    def _make_plan(self, **overrides) -> DialogueResponsePlan:
        defaults = {
            "response_id": "test",
            "speaker_id": "npc",
            "primary_act": "refusal",
            "framing": {"tone": "hostile", "stance": "aggressive", "reveal_level": "none", "urgency": "normal"},
            "text_slots": {"line": "No.", "summary": "refusal (hostile/aggressive)"},
            "hint_targets": [],
            "state_drivers": {"hostility": "high"},
            "trace": {"selected_act": "refusal"},
            "allowed_topics": [],
            "blocked_topics": ["arc_1"],
        }
        defaults.update(overrides)
        return DialogueResponsePlan(**defaults)

    def test_present_response_is_player_safe(self):
        presenter = DialoguePresenter()
        plan = self._make_plan()
        result = presenter.present_response(plan)
        assert "speaker_id" in result
        assert "act" in result
        assert "line" in result
        assert "tone" in result
        assert "stance" in result
        # Internal reasoning should NOT leak
        assert "state_drivers" not in result
        assert "blocked_topics" not in result

    def test_present_trace_has_reasoning(self):
        presenter = DialoguePresenter()
        plan = self._make_plan()
        trace = presenter.present_trace(plan)
        assert "primary_act" in trace
        assert "state_drivers" in trace
        assert "decision_reasons" in trace
        assert "reveal_policy" in trace

    def test_present_log_entry_for_journalable_act(self):
        presenter = DialoguePresenter()
        plan = self._make_plan(primary_act="threat")
        entry = presenter.present_log_entry(plan, tick=5)
        assert entry is not None
        assert entry["act"] == "threat"
        assert entry["tick"] == 5

    def test_present_log_entry_none_for_acknowledge(self):
        presenter = DialoguePresenter()
        plan = self._make_plan(primary_act="acknowledge")
        entry = presenter.present_log_entry(plan)
        assert entry is None

    def test_present_log_entry_none_for_probe(self):
        presenter = DialoguePresenter()
        plan = self._make_plan(primary_act="probe")
        entry = presenter.present_log_entry(plan)
        assert entry is None


# ======================================================================
# Core façade tests
# ======================================================================

class TestDialogueCore:
    """DialogueCore end-to-end unit tests."""

    def test_build_interaction_response_returns_three_keys(self):
        core = DialogueCore()
        result = core.build_interaction_response(speaker_id="npc")
        assert "response" in result
        assert "trace" in result
        assert "log_entry" in result

    def test_response_has_expected_fields(self):
        core = DialogueCore()
        result = core.build_interaction_response(
            speaker_id="npc",
            npc_decision={"outcome": "refuse"},
        )
        resp = result["response"]
        assert resp["act"] == "refusal"
        assert "line" in resp

    def test_deterministic_output(self):
        core = DialogueCore()
        kwargs = dict(
            speaker_id="npc",
            listener_id="player",
            npc_decision={"outcome": "agree"},
            scene_summary={"location": "market"},
        )
        r1 = core.build_interaction_response(**kwargs)
        r2 = core.build_interaction_response(**kwargs)
        assert r1 == r2

    def test_threat_produces_log_entry(self):
        core = DialogueCore()
        result = core.build_interaction_response(
            speaker_id="npc",
            npc_decision={"outcome": "threaten"},
        )
        assert result["log_entry"] is not None
        assert result["log_entry"]["act"] == "threat"

    def test_acknowledge_produces_no_log_entry(self):
        core = DialogueCore()
        result = core.build_interaction_response(speaker_id="npc")
        assert result["log_entry"] is None


# ======================================================================
# Journal builder dialogue entry tests
# ======================================================================

class TestJournalBuilderDialogueEntry:
    """Test JournalBuilder.build_dialogue_log_entry."""

    def test_journalable_act_produces_entry(self):
        from app.rpg.memory.journal_builder import JournalBuilder
        builder = JournalBuilder()
        entry = builder.build_dialogue_log_entry(
            {"act": "threat", "speaker_id": "npc", "summary": "Threatened player"},
            tick=3,
            location="cave",
        )
        assert entry is not None
        assert entry.entry_type == "dialogue"
        assert entry.location == "cave"
        assert entry.metadata["act"] == "threat"

    def test_non_journalable_act_returns_none(self):
        from app.rpg.memory.journal_builder import JournalBuilder
        builder = JournalBuilder()
        entry = builder.build_dialogue_log_entry(
            {"act": "acknowledge", "speaker_id": "npc"},
        )
        assert entry is None

    def test_refusal_produces_entry(self):
        from app.rpg.memory.journal_builder import JournalBuilder
        builder = JournalBuilder()
        entry = builder.build_dialogue_log_entry(
            {"act": "refusal", "speaker_id": "npc", "summary": "Refused help"},
        )
        assert entry is not None


# ======================================================================
# CampaignMemoryCore dialogue recording tests
# ======================================================================

class TestCampaignMemoryCoreDialogue:
    """Test CampaignMemoryCore.record_dialogue_log_entry."""

    def test_record_meaningful_dialogue(self):
        from app.rpg.memory.core import CampaignMemoryCore
        core = CampaignMemoryCore()
        assert len(core.journal_entries) == 0
        core.record_dialogue_log_entry(
            {"act": "threat", "speaker_id": "npc", "summary": "Threatened"},
            tick=1,
        )
        assert len(core.journal_entries) == 1
        assert core.journal_entries[0].entry_type == "dialogue"

    def test_skip_trivial_dialogue(self):
        from app.rpg.memory.core import CampaignMemoryCore
        core = CampaignMemoryCore()
        core.record_dialogue_log_entry(
            {"act": "acknowledge", "speaker_id": "npc"},
        )
        assert len(core.journal_entries) == 0
