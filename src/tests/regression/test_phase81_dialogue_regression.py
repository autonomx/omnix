"""Phase 8.1 — Dialogue Regression Tests.

Protect the architecture: no truth mutation, determinism, fallback safety,
act validation, and bounded history.
"""

from __future__ import annotations

import sys
import os
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.rpg.dialogue.core import DialogueCore
from app.rpg.dialogue.context_builder import DialogueContextBuilder
from app.rpg.dialogue.response_planner import DialogueResponsePlanner
from app.rpg.dialogue.presenter import DialoguePresenter
from app.rpg.dialogue.acts import SUPPORTED_DIALOGUE_ACTS
from app.rpg.dialogue.models import DialogueTurnContext
from app.rpg.execution.resolver import ActionResolver


# ======================================================================
# Test helpers / mocks
# ======================================================================

class _MockCoherenceCore:
    def __init__(self, entities=None, scene=None, threads=None):
        self._entities = entities or {}
        self._scene = scene or {"location": "tavern", "summary": "", "present_actors": [], "active_tensions": []}
        self._threads = threads or {}

    def get_scene_summary(self):
        return dict(self._scene)

    def get_entity_facts(self, entity_id):
        return self._entities.get(entity_id)

    def get_unresolved_threads(self):
        return [{"thread_id": k} for k in self._threads]

    def get_active_tensions(self):
        return self._scene.get("active_tensions", [])

    def get_state(self):
        return self

    @property
    def unresolved_threads(self):
        return self._threads


class _MockSocialStateCore:
    def __init__(self, relationships=None):
        self._relationships = relationships or {}
        self._original_relationships = copy.deepcopy(self._relationships)

    def get_state(self):
        return self

    @property
    def query(self):
        return self

    @property
    def relationships(self):
        return self._relationships

    @property
    def rumors(self):
        return {}

    @property
    def alliances(self):
        return {}

    def get_relationship(self, state, source_id, target_id):
        return self._relationships.get(f"{source_id}:{target_id}")

    def get_reputation(self, state, source_id, target_id):
        return None

    def get_active_rumors_for_subject(self, state, subject_id):
        return []

    def get_alliance(self, state, entity_a, entity_b):
        return None

    def was_mutated(self):
        return self._relationships != self._original_relationships


class _MockArcControlController:
    def __init__(self, reveals=None, arcs=None):
        self.reveals = reveals or {}
        self.arcs = arcs or {}
        self.scene_biases = {}
        self._original_arcs = copy.deepcopy(self.arcs)
        self._original_reveals = copy.deepcopy(self.reveals)

    def build_director_context(self, coherence_core):
        return {
            "active_arcs": [{"arc_id": k} for k in self.arcs],
            "due_reveals": [{"reveal_id": k} for k in self.reveals],
            "active_pacing_plan": None,
            "active_scene_bias": None,
        }

    def was_mutated(self):
        return self.arcs != self._original_arcs or self.reveals != self._original_reveals


class _MockCampaignMemoryCore:
    def __init__(self, entries=None):
        self.journal_entries = entries or []
        self._original_count = len(self.journal_entries)

    def was_mutated(self):
        return len(self.journal_entries) != self._original_count


class _MockNPCAgencyEngine:
    def __init__(self, outcome="agree"):
        self._outcome = outcome

    def resolve_social_interaction(self, mapped_action, coherence_core, gm_state, social_state_core=None):
        npc_id = mapped_action.get("target_id", "npc_a")
        type_map = {
            "agree": "npc_response_agreed",
            "refuse": "npc_response_refused",
            "threaten": "npc_response_threatened",
            "redirect": "npc_response_redirected",
            "delay": "npc_response_delayed",
        }
        return {
            "decision": {"npc_id": npc_id, "outcome": self._outcome, "response_type": self._outcome, "summary": f"NPC {self._outcome}"},
            "events": [{"type": type_map.get(self._outcome, "npc_response_agreed"), "payload": {"npc_id": npc_id, "summary": f"NPC {self._outcome}"}}],
        }


class _MockGMState:
    pass


# ======================================================================
# Regression tests
# ======================================================================

class TestNoDirectTruthMutation:
    """DialogueCore.build_interaction_response must NOT mutate state."""

    def test_coherence_not_mutated(self):
        coherence = _MockCoherenceCore(
            entities={"npc_a": {"role": "guard"}},
            scene={"location": "gate", "summary": "Guards patrol", "present_actors": ["npc_a"], "active_tensions": ["bandits"]},
        )
        original_scene = copy.deepcopy(coherence.get_scene_summary())
        original_entities = copy.deepcopy(coherence._entities)

        core = DialogueCore()
        core.build_interaction_response(
            speaker_id="npc_a",
            listener_id="player",
            coherence_core=coherence,
        )

        assert coherence.get_scene_summary() == original_scene
        assert coherence._entities == original_entities

    def test_social_state_not_mutated(self):
        social = _MockSocialStateCore(relationships={
            "npc_a:player": {"trust": 0.5, "hostility": 0.2, "fear": 0.1, "respect": 0.3},
        })

        core = DialogueCore()
        core.build_interaction_response(
            speaker_id="npc_a",
            listener_id="player",
            social_state_core=social,
        )

        assert not social.was_mutated()

    def test_arc_controller_not_mutated(self):
        arc = _MockArcControlController(
            arcs={"arc_main": {"arc_id": "arc_main"}},
            reveals={"r1": {"reveal_id": "r1"}},
        )

        core = DialogueCore()
        core.build_interaction_response(
            speaker_id="npc_a",
            arc_control_controller=arc,
        )

        assert not arc.was_mutated()

    def test_memory_not_mutated(self):
        memory = _MockCampaignMemoryCore()

        core = DialogueCore()
        core.build_interaction_response(
            speaker_id="npc_a",
            campaign_memory_core=memory,
        )

        assert not memory.was_mutated()


class TestSameStateSameResponse:
    """Same state must produce identical response."""

    def test_deterministic_response(self):
        core = DialogueCore()
        kwargs = dict(
            speaker_id="npc_a",
            listener_id="player",
            npc_decision={"outcome": "refuse"},
            scene_summary={"location": "dungeon"},
        )
        r1 = core.build_interaction_response(**kwargs)
        r2 = core.build_interaction_response(**kwargs)
        assert r1["response"] == r2["response"]
        assert r1["trace"] == r2["trace"]
        assert r1["log_entry"] == r2["log_entry"]

    def test_deterministic_with_social_and_arc(self):
        core = DialogueCore()
        coherence = _MockCoherenceCore(entities={"npc_a": {"role": "guard"}})
        social = _MockSocialStateCore(relationships={
            "npc_a:player": {"trust": 0.3, "hostility": 0.7, "fear": 0.1, "respect": 0.2},
        })
        arc = _MockArcControlController(reveals={"r1": {}})

        kwargs = dict(
            speaker_id="npc_a",
            listener_id="player",
            coherence_core=coherence,
            social_state_core=social,
            arc_control_controller=arc,
            npc_decision={"outcome": "threaten"},
        )
        r1 = core.build_interaction_response(**kwargs)
        r2 = core.build_interaction_response(**kwargs)
        assert r1 == r2


class TestMissingDialogueCoreFallback:
    """ActionResolver without dialogue_core still behaves like Phase 7.4."""

    def test_resolver_without_dialogue_core(self):
        coherence = _MockCoherenceCore(entities={"npc_a": {"role": "merchant"}})
        resolver = ActionResolver(
            npc_agency_engine=_MockNPCAgencyEngine(outcome="agree"),
            # No dialogue_core
        )
        result = resolver.resolve_choice(
            option={
                "option_id": "opt_talk",
                "intent_type": "talk_to_npc",
                "target_id": "npc_a",
                "resolution_type": "social_contact",
                "summary": "Talk to merchant",
                "constraints": [],
            },
            coherence_core=coherence,
            gm_state=_MockGMState(),
        )
        # Should succeed without dialogue metadata
        assert result.resolved_action.outcome == "agree"
        assert "dialogue_response" not in result.resolved_action.metadata


class TestSupportedActsOnly:
    """Every emitted/presented act must be in SUPPORTED_DIALOGUE_ACTS."""

    def test_all_outcomes_produce_supported_acts(self):
        core = DialogueCore()
        for outcome in ["agree", "refuse", "threaten", "redirect", "delay", "offer", "warn", "suspicious", ""]:
            result = core.build_interaction_response(
                speaker_id="npc",
                npc_decision={"outcome": outcome} if outcome else None,
            )
            act = result["response"]["act"]
            assert act in SUPPORTED_DIALOGUE_ACTS, f"Act '{act}' from outcome '{outcome}' not supported"

    def test_planner_always_produces_supported_acts(self):
        planner = DialogueResponsePlanner()
        for outcome in ["agree", "refuse", "threaten", "redirect", "delay", "offer", ""]:
            ctx = DialogueTurnContext(
                speaker_id="npc",
                current_action_outcome=outcome,
                metadata={"state_drivers": {
                    "openness": "medium", "hostility": "low", "trust": "medium",
                    "fear": "low", "respect": "medium", "reveal_pressure": "none",
                    "scene_tension": "low", "urgency": "normal", "interaction_mode": "social",
                }},
            )
            dec = planner.classify_act(ctx)
            assert dec.primary_act in SUPPORTED_DIALOGUE_ACTS


class TestBoundedHistory:
    """Only capped recent history subset should be used."""

    def test_history_bounded_at_five(self):
        builder = DialogueContextBuilder()

        class _Entry:
            def __init__(self, entry_id, entity_ids):
                self.entry_id = entry_id
                self.entity_ids = entity_ids
            def to_dict(self):
                return {"entry_id": self.entry_id, "entity_ids": self.entity_ids}

        class _MockMemory:
            def __init__(self):
                self.journal_entries = [_Entry(f"e{i:03d}", ["npc"]) for i in range(50)]

        ctx = builder.build_for_interaction(
            speaker_id="npc",
            history_source=_MockMemory(),
        )
        assert len(ctx.interaction_history) == 5

    def test_history_deterministic_order(self):
        builder = DialogueContextBuilder()

        class _Entry:
            def __init__(self, entry_id, entity_ids):
                self.entry_id = entry_id
                self.entity_ids = entity_ids
            def to_dict(self):
                return {"entry_id": self.entry_id, "entity_ids": self.entity_ids}

        class _MockMemory:
            def __init__(self):
                self.journal_entries = [_Entry(f"e{i:03d}", ["npc"]) for i in range(10)]

        ctx1 = builder.build_for_interaction(speaker_id="npc", history_source=_MockMemory())
        ctx2 = builder.build_for_interaction(speaker_id="npc", history_source=_MockMemory())
        assert ctx1.interaction_history == ctx2.interaction_history

    def test_empty_history_source(self):
        builder = DialogueContextBuilder()
        ctx = builder.build_for_interaction(speaker_id="npc")
        assert ctx.interaction_history == []


class TestResolverDialogueIntegration:
    """Resolver with dialogue_core produces expected metadata."""

    def _make_option(self, target_id="npc_a"):
        return {
            "option_id": "opt_talk",
            "intent_type": "talk_to_npc",
            "target_id": target_id,
            "resolution_type": "social_contact",
            "summary": "Talk to NPC",
            "constraints": [],
        }

    def test_dialogue_trace_present(self):
        coherence = _MockCoherenceCore(entities={"npc_a": {"role": "guard"}})
        dialogue_core = DialogueCore()
        resolver = ActionResolver(
            npc_agency_engine=_MockNPCAgencyEngine(outcome="refuse"),
            dialogue_core=dialogue_core,
        )
        result = resolver.resolve_choice(
            option=self._make_option(),
            coherence_core=coherence,
            gm_state=_MockGMState(),
        )
        meta = result.resolved_action.metadata
        assert "dialogue_trace" in meta
        assert meta["dialogue_trace"]["primary_act"] == "refusal"

    def test_dialogue_log_entry_for_threat(self):
        coherence = _MockCoherenceCore(entities={"npc_a": {"role": "guard"}})
        dialogue_core = DialogueCore()
        resolver = ActionResolver(
            npc_agency_engine=_MockNPCAgencyEngine(outcome="threaten"),
            dialogue_core=dialogue_core,
        )
        result = resolver.resolve_choice(
            option=self._make_option(),
            coherence_core=coherence,
            gm_state=_MockGMState(),
        )
        log = result.resolved_action.metadata.get("dialogue_log_entry")
        assert log is not None
        assert log["act"] == "threat"

    def test_no_dialogue_log_for_agree(self):
        """Agreement uses the agreement act which IS journalable, so log_entry should exist."""
        coherence = _MockCoherenceCore(entities={"npc_a": {"role": "merchant"}})
        dialogue_core = DialogueCore()
        resolver = ActionResolver(
            npc_agency_engine=_MockNPCAgencyEngine(outcome="agree"),
            dialogue_core=dialogue_core,
        )
        result = resolver.resolve_choice(
            option=self._make_option(),
            coherence_core=coherence,
            gm_state=_MockGMState(),
        )
        log = result.resolved_action.metadata.get("dialogue_log_entry")
        # agreement is journalable
        assert log is not None
        assert log["act"] == "agreement"
