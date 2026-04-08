"""Phase 8.1 — Dialogue Functional Tests.

Lightweight functional scenarios following the style of
test_phase74_* and test_phase80_* tests.
"""

from __future__ import annotations

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.rpg.dialogue.acts import SUPPORTED_DIALOGUE_ACTS
from app.rpg.dialogue.core import DialogueCore
from app.rpg.execution.models import ResolvedAction
from app.rpg.execution.resolver import ActionResolver

# ======================================================================
# Test helpers / mocks
# ======================================================================

class _MockCoherenceCore:
    """Minimal coherence core mock for functional tests."""

    def __init__(self, entities=None, scene=None):
        self._entities = entities or {}
        self._scene = scene or {"location": "tavern", "summary": "", "present_actors": [], "active_tensions": []}

    def get_scene_summary(self):
        return dict(self._scene)

    def get_entity_facts(self, entity_id):
        return self._entities.get(entity_id)

    def get_unresolved_threads(self):
        return []

    def get_active_tensions(self):
        return self._scene.get("active_tensions", [])


class _MockSocialStateCore:
    """Minimal social state core mock."""

    def __init__(self, relationships=None):
        self._relationships = relationships or {}

    def get_state(self):
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

    @property
    def query(self):
        return self

    def get_relationship(self, state, source_id, target_id):
        key = f"{source_id}:{target_id}"
        return self._relationships.get(key)

    def get_reputation(self, state, source_id, target_id):
        return None

    def get_active_rumors_for_subject(self, state, subject_id):
        return []

    def get_alliance(self, state, entity_a, entity_b):
        return None


class _MockArcControlController:
    """Minimal arc control mock."""

    def __init__(self, reveals=None, arcs=None):
        self.reveals = reveals or {}
        self.arcs = arcs or {}
        self.scene_biases = {}

    def build_director_context(self, coherence_core):
        due = [{"reveal_id": k} for k in self.reveals]
        return {
            "active_arcs": [{"arc_id": k} for k in self.arcs],
            "due_reveals": due,
            "active_pacing_plan": None,
            "active_scene_bias": None,
        }


class _MockNPCAgencyEngine:
    """Minimal NPC agency engine for functional tests."""

    def __init__(self, outcome="agree"):
        self._outcome = outcome

    def resolve_social_interaction(self, mapped_action, coherence_core, gm_state, social_state_core=None):
        npc_id = mapped_action.get("target_id", "npc_a")
        event_type_map = {
            "agree": "npc_response_agreed",
            "refuse": "npc_response_refused",
            "threaten": "npc_response_threatened",
            "redirect": "npc_response_redirected",
            "delay": "npc_response_delayed",
        }
        return {
            "decision": {
                "npc_id": npc_id,
                "outcome": self._outcome,
                "response_type": self._outcome,
                "summary": f"NPC {self._outcome}",
            },
            "events": [{
                "type": event_type_map.get(self._outcome, "npc_response_agreed"),
                "payload": {"npc_id": npc_id, "summary": f"NPC {self._outcome}"},
            }],
        }


class _MockGMState:
    pass


# ======================================================================
# Functional scenarios
# ======================================================================

class TestSocialInteractionReturnsStructuredDialogue:
    """Resolve a talk_to_npc option and assert structured dialogue payload."""

    def _make_option(self, target_id="npc_a"):
        return {
            "option_id": "opt_talk",
            "intent_type": "talk_to_npc",
            "target_id": target_id,
            "resolution_type": "social_contact",
            "summary": "Talk to NPC",
            "constraints": [],
        }

    def test_dialogue_response_exists(self):
        coherence = _MockCoherenceCore(entities={"npc_a": {"role": "merchant", "name": "Arlo"}})
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
        meta = result.resolved_action.metadata
        assert "dialogue_response" in meta
        assert meta["dialogue_response"] is not None

    def test_response_has_act_tone_summary_line(self):
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
        resp = result.resolved_action.metadata["dialogue_response"]
        assert "act" in resp
        assert "tone" in resp
        assert "summary" in resp
        assert "line" in resp

    def test_no_unsafe_metadata_leaks(self):
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
        resp = result.resolved_action.metadata["dialogue_response"]
        # Player-safe payload should not contain internal state_drivers or blocked_topics
        assert "state_drivers" not in resp
        assert "blocked_topics" not in resp


class TestAgreementRefusalThreatRedirectDistinguishable:
    """Different NPC outcomes produce distinct dialogue acts."""

    def _resolve_with_outcome(self, outcome):
        coherence = _MockCoherenceCore(entities={"npc_a": {"role": "guard"}})
        dialogue_core = DialogueCore()
        resolver = ActionResolver(
            npc_agency_engine=_MockNPCAgencyEngine(outcome=outcome),
            dialogue_core=dialogue_core,
        )
        result = resolver.resolve_choice(
            option={
                "option_id": "opt_talk",
                "intent_type": "talk_to_npc",
                "target_id": "npc_a",
                "resolution_type": "social_contact",
                "summary": "Talk to guard",
                "constraints": [],
            },
            coherence_core=coherence,
            gm_state=_MockGMState(),
        )
        return result.resolved_action.metadata.get("dialogue_response", {})

    def test_agree_gives_agreement(self):
        resp = self._resolve_with_outcome("agree")
        assert resp["act"] == "agreement"

    def test_refuse_gives_refusal(self):
        resp = self._resolve_with_outcome("refuse")
        assert resp["act"] == "refusal"

    def test_threaten_gives_threat(self):
        resp = self._resolve_with_outcome("threaten")
        assert resp["act"] == "threat"

    def test_redirect_gives_redirect(self):
        resp = self._resolve_with_outcome("redirect")
        assert resp["act"] == "redirect"


class TestUXPayloadIncludesInteraction:
    """After resolution, UX payload should include interaction section."""

    def test_scene_payload_has_interaction(self):
        from app.rpg.ux.payload_builder import UXPayloadBuilder

        class _QueryStub:
            def get_active_threads(self):
                return []

        class _CoherenceStub:
            query = _QueryStub()
            def get_scene_summary(self):
                return {}

        class _FakeLoop:
            tick_count = 1
            coherence_core = _CoherenceStub()
            last_dialogue_response = {"act": "agreement", "line": "Sure."}
            gameplay_control_controller = None
            campaign_memory_core = None
            social_state_core = None
            arc_control_controller = None
            pack_registry = None

        builder = UXPayloadBuilder()
        payload = builder.build_scene_payload(_FakeLoop())
        assert payload.interaction.get("act") == "agreement"
        assert payload.interaction.get("line") == "Sure."

    def test_action_result_payload_has_interaction(self):
        from app.rpg.ux.payload_builder import UXPayloadBuilder

        class _FakeLoop:
            tick_count = 1
            coherence_core = _MockCoherenceCore()
            last_dialogue_response = {"act": "threat", "line": "Leave."}
            gameplay_control_controller = None
            campaign_memory_core = None
            social_state_core = None
            arc_control_controller = None
            pack_registry = None

        builder = UXPayloadBuilder()
        payload = builder.build_action_result_payload(_FakeLoop(), {"choice_id": "x"})
        assert payload.interaction.get("act") == "threat"


class TestJournalOnlyRecordsMeaningful:
    """Journal integration should only record meaningful interactions."""

    def test_threat_produces_journal_entry(self):
        from app.rpg.memory.core import CampaignMemoryCore
        core = CampaignMemoryCore()
        core.record_dialogue_log_entry(
            {"act": "threat", "speaker_id": "npc", "summary": "Threatened"},
            tick=1,
        )
        assert len(core.journal_entries) == 1

    def test_reveal_hint_produces_journal_entry(self):
        from app.rpg.memory.core import CampaignMemoryCore
        core = CampaignMemoryCore()
        core.record_dialogue_log_entry(
            {"act": "reveal_hint", "speaker_id": "npc", "summary": "Hinted at secret"},
            tick=2,
        )
        assert len(core.journal_entries) == 1

    def test_acknowledge_does_not_produce_journal_entry(self):
        from app.rpg.memory.core import CampaignMemoryCore
        core = CampaignMemoryCore()
        core.record_dialogue_log_entry(
            {"act": "acknowledge", "speaker_id": "npc"},
        )
        assert len(core.journal_entries) == 0

    def test_stall_does_not_produce_journal_entry(self):
        from app.rpg.memory.core import CampaignMemoryCore
        core = CampaignMemoryCore()
        core.record_dialogue_log_entry(
            {"act": "stall", "speaker_id": "npc"},
        )
        assert len(core.journal_entries) == 0


class TestDialogueReflectsArcPressure:
    """Dialogue response should reflect arc reveal pressure."""

    def test_reveal_pressure_shifts_act(self):
        dialogue_core = DialogueCore()
        arc = _MockArcControlController(
            reveals={"r1": {"reveal_id": "r1"}},
            arcs={"arc_main": {"arc_id": "arc_main"}},
        )
        # Provide a cooperative relationship so trust is not "low"
        social = _MockSocialStateCore(relationships={
            "npc_a:player": {"trust": 0.7, "hostility": 0.0, "fear": 0.0, "respect": 0.3},
        })
        result = dialogue_core.build_interaction_response(
            speaker_id="npc_a",
            listener_id="player",
            arc_control_controller=arc,
            social_state_core=social,
        )
        # With high reveal pressure and cooperative relationship, should get reveal_hint
        assert result["response"]["act"] == "reveal_hint"

    def test_no_reveal_pressure_gives_acknowledge(self):
        dialogue_core = DialogueCore()
        result = dialogue_core.build_interaction_response(
            speaker_id="npc_a",
        )
        assert result["response"]["act"] == "acknowledge"
