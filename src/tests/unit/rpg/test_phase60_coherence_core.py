"""Phase 6.0 — Coherence Core: Unit tests.

Tests the coherence models, reducers, contradiction detector, query API,
and core engine in isolation. No external services required.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.coherence.models import (
    CoherenceMutation,
    CoherenceState,
    CoherenceUpdateResult,
    CommitmentRecord,
    ConsequenceRecord,
    ContradictionRecord,
    EntityCoherenceView,
    SceneAnchor,
    ThreadRecord,
)
from app.rpg.coherence import CoherenceCore
from app.rpg.coherence.models import FactRecord
from app.rpg.coherence.reducers import (
    REDUCERS,
    normalize_event,
    reduce_character_death,
    reduce_commitment_broken,
    reduce_commitment_created,
    reduce_event,
    reduce_item_acquired,
    reduce_item_lost,
    reduce_npc_moved,
    reduce_relationship_changed,
    reduce_scene_generated,
    reduce_scene_started,
    reduce_thread_resolved,
    reduce_thread_started,
)
from app.rpg.coherence.detector import ContradictionDetector
from app.rpg.coherence.query import CoherenceQueryAPI
from app.rpg.coherence.core import CoherenceCore, AUTHORITY_RANK
from app.rpg.core.event_bus import Event


def test_character_death_persists_as_canonical_fact():
    core = CoherenceCore()
    core.apply_event(
        Event("character_died", {"entity_id": "guard"}, source="test", event_id="e1", tick=1)
    )
    facts = core.get_known_facts("guard")["facts"]
    alive_facts = [f for f in facts if f["predicate"] == "alive"]
    assert alive_facts[0]["value"] is False


def test_lower_authority_fact_cannot_overwrite_higher_authority_fact():
    core = CoherenceCore()
    core.insert_fact(
        FactRecord(
            fact_id="guard:location",
            category="world",
            subject="guard",
            predicate="location",
            value="gate",
            authority="creator_canon",
        )
    )
    core.apply_event(
        Event("npc_moved", {"npc_id": "guard", "location": "tower"}, source="test", event_id="e2", tick=2)
    )
    facts = core.get_known_facts("guard")["facts"]
    loc = [f for f in facts if f["predicate"] == "location"]
    assert loc[0]["value"] == "gate"


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestFactRecord:
    def test_create_fact(self):
        fact = FactRecord(
            fact_id="npc_guard:location",
            category="world",
            subject="npc_guard",
            predicate="location",
            value="gate",
        )
        assert fact.fact_id == "npc_guard:location"
        assert fact.confidence == 1.0
        assert fact.status == "confirmed"
        assert fact.authority == "runtime"

    def test_to_dict_roundtrip(self):
        fact = FactRecord(
            fact_id="f1", category="world", subject="npc", predicate="alive",
            value=True, confidence=0.9, authority="event_confirmed",
            tick_first_seen=1, tick_last_updated=3,
        )
        d = fact.to_dict()
        restored = FactRecord.from_dict(d)
        assert restored.fact_id == "f1"
        assert restored.value is True
        assert restored.confidence == 0.9
        assert restored.tick_first_seen == 1

    def test_default_metadata(self):
        fact = FactRecord(fact_id="x", category="y", subject="z", predicate="p", value=1)
        assert fact.metadata == {}


class TestThreadRecord:
    def test_create_thread(self):
        thread = ThreadRecord(thread_id="t1", title="Find the relic")
        assert thread.status == "unresolved"
        assert thread.priority == "normal"
        assert thread.notes == []

    def test_roundtrip(self):
        thread = ThreadRecord(thread_id="t1", title="Rescue", opened_tick=5, notes=["started"])
        d = thread.to_dict()
        restored = ThreadRecord.from_dict(d)
        assert restored.thread_id == "t1"
        assert restored.notes == ["started"]


class TestCommitmentRecord:
    def test_create_commitment(self):
        c = CommitmentRecord(
            commitment_id="c1", actor_id="player", target_id="npc_guard",
            kind="promise_made", text="I will return",
        )
        assert c.status == "active"
        assert c.broken_tick is None

    def test_roundtrip(self):
        c = CommitmentRecord(
            commitment_id="c1", actor_id="npc", target_id="player",
            kind="threat_made", text="Watch yourself",
        )
        d = c.to_dict()
        restored = CommitmentRecord.from_dict(d)
        assert restored.commitment_id == "c1"
        assert restored.kind == "threat_made"


class TestSceneAnchor:
    def test_create_anchor(self):
        a = SceneAnchor(anchor_id="a1", tick=5, location="market")
        assert a.present_actors == []
        assert a.summary == ""

    def test_roundtrip(self):
        a = SceneAnchor(
            anchor_id="a1", tick=3, location="tavern",
            present_actors=["player", "guard"],
            active_tensions=["threat from bandits"],
        )
        d = a.to_dict()
        restored = SceneAnchor.from_dict(d)
        assert restored.present_actors == ["player", "guard"]
        assert restored.active_tensions == ["threat from bandits"]


class TestConsequenceRecord:
    def test_create(self):
        c = ConsequenceRecord(consequence_id="cons1", event_id="e1", tick=1, summary="Fire started")
        assert c.consequence_type == "general"

    def test_roundtrip(self):
        c = ConsequenceRecord(
            consequence_id="cons1", event_id="e1", tick=1,
            summary="NPC died", entity_ids=["guard"],
        )
        d = c.to_dict()
        restored = ConsequenceRecord.from_dict(d)
        assert restored.entity_ids == ["guard"]


class TestContradictionRecord:
    def test_create(self):
        c = ContradictionRecord(
            contradiction_id="ct1", contradiction_type="dead_actor_conflict",
            severity="high", message="Dead NPC moved",
        )
        assert c.entity_ids == []

    def test_roundtrip(self):
        c = ContradictionRecord(
            contradiction_id="ct1", contradiction_type="location_conflict",
            severity="warning", message="NPC in two places",
            entity_ids=["guard"], related_fact_ids=["guard:location"],
        )
        d = c.to_dict()
        restored = ContradictionRecord.from_dict(d)
        assert restored.related_fact_ids == ["guard:location"]


class TestEntityCoherenceView:
    def test_create(self):
        v = EntityCoherenceView(entity_id="guard")
        assert v.facts == []
        assert v.commitments == []

    def test_roundtrip(self):
        v = EntityCoherenceView(
            entity_id="guard",
            facts=[{"fact_id": "f1"}],
            commitments=[{"commitment_id": "c1"}],
        )
        d = v.to_dict()
        restored = EntityCoherenceView.from_dict(d)
        assert len(restored.facts) == 1


class TestCoherenceMutation:
    def test_create(self):
        m = CoherenceMutation(action="upsert_fact", target="world", data={"fact_id": "f1"})
        assert m.action == "upsert_fact"

    def test_roundtrip(self):
        m = CoherenceMutation(action="resolve_thread", target="thread", data={"thread_id": "t1"})
        d = m.to_dict()
        restored = CoherenceMutation.from_dict(d)
        assert restored.data["thread_id"] == "t1"


class TestCoherenceUpdateResult:
    def test_empty(self):
        r = CoherenceUpdateResult()
        assert r.events_applied == 0
        assert r.mutations == []
        assert r.contradictions == []

    def test_roundtrip(self):
        r = CoherenceUpdateResult(
            events_applied=2,
            mutations=[CoherenceMutation(action="upsert_fact", target="world", data={"fact_id": "f1"})],
            contradictions=[ContradictionRecord(
                contradiction_id="ct1", contradiction_type="test", severity="info", message="test",
            )],
        )
        d = r.to_dict()
        restored = CoherenceUpdateResult.from_dict(d)
        assert restored.events_applied == 2
        assert len(restored.mutations) == 1
        assert len(restored.contradictions) == 1


class TestCoherenceState:
    def test_empty_state(self):
        state = CoherenceState()
        assert state.stable_world_facts == {}
        assert state.contradictions == []

    def test_full_roundtrip(self):
        state = CoherenceState()
        state.stable_world_facts["guard:location"] = FactRecord(
            fact_id="guard:location", category="world", subject="guard",
            predicate="location", value="gate",
        )
        state.unresolved_threads["t1"] = ThreadRecord(thread_id="t1", title="Quest")
        state.player_commitments["c1"] = CommitmentRecord(
            commitment_id="c1", actor_id="player", target_id="npc",
            kind="promise", text="I'll help",
        )
        state.continuity_anchors.append(SceneAnchor(anchor_id="a1", tick=1, location="market"))
        state.contradictions.append(ContradictionRecord(
            contradiction_id="ct1", contradiction_type="test", severity="info", message="test",
        ))

        d = state.to_dict()
        restored = CoherenceState.from_dict(d)
        assert "guard:location" in restored.stable_world_facts
        assert "t1" in restored.unresolved_threads
        assert "c1" in restored.player_commitments
        assert len(restored.continuity_anchors) == 1
        assert len(restored.contradictions) == 1


# ---------------------------------------------------------------------------
# Reducer Tests
# ---------------------------------------------------------------------------

class TestNormalizeEvent:
    def test_normalize_event_object(self):
        evt = Event("npc_moved", {"npc_id": "guard", "location": "gate"}, source="test", event_id="e1", tick=5)
        n = normalize_event(evt)
        assert n["type"] == "npc_moved"
        assert n["payload"]["npc_id"] == "guard"
        assert n["event_id"] == "e1"
        assert n["tick"] == 5

    def test_normalize_dict(self):
        d = {"type": "item_acquired", "payload": {"item_id": "sword"}, "event_id": "e2", "tick": 3}
        n = normalize_event(d)
        assert n["type"] == "item_acquired"
        assert n["event_id"] == "e2"

    def test_normalize_dict_tick_from_payload(self):
        d = {"type": "test", "payload": {"tick": 7}}
        n = normalize_event(d)
        assert n["tick"] == 7

    def test_normalize_unsupported_type(self):
        import pytest
        with pytest.raises(TypeError):
            normalize_event(42)


class TestReduceSceneStarted:
    def test_produces_location_fact_and_anchor(self):
        state = CoherenceState()
        event = {"type": "scene_started", "payload": {"location": "tavern"}, "event_id": "e1", "tick": 1}
        mutations = reduce_scene_started(state, event)
        actions = [m.action for m in mutations]
        assert "upsert_fact" in actions
        assert "push_anchor" in actions

    def test_no_location_still_pushes_anchor(self):
        state = CoherenceState()
        event = {"type": "scene_started", "payload": {}, "event_id": "e1", "tick": 1}
        mutations = reduce_scene_started(state, event)
        assert any(m.action == "push_anchor" for m in mutations)
        assert not any(m.action == "upsert_fact" for m in mutations)


class TestReduceSceneGenerated:
    def test_produces_anchor_and_consequence(self):
        state = CoherenceState()
        event = {"type": "scene_generated", "payload": {"scene": {"location": "forest"}}, "event_id": "e1", "tick": 2}
        mutations = reduce_scene_generated(state, event)
        actions = [m.action for m in mutations]
        assert "push_anchor" in actions
        assert "record_consequence" in actions


class TestReduceNPCMoved:
    def test_produces_location_fact(self):
        state = CoherenceState()
        event = {"type": "npc_moved", "payload": {"npc_id": "guard", "location": "market"}, "event_id": "e1", "tick": 1}
        mutations = reduce_npc_moved(state, event)
        assert len(mutations) == 1
        assert mutations[0].data["fact_id"] == "guard:location"
        assert mutations[0].data["value"] == "market"

    def test_empty_if_no_npc_id(self):
        state = CoherenceState()
        event = {"type": "npc_moved", "payload": {"location": "market"}, "event_id": "e1", "tick": 1}
        assert reduce_npc_moved(state, event) == []

    def test_alternative_keys(self):
        state = CoherenceState()
        event = {"type": "npc_moved", "payload": {"actor_id": "guard", "to": "gate"}, "event_id": "e1", "tick": 1}
        mutations = reduce_npc_moved(state, event)
        assert mutations[0].data["value"] == "gate"


class TestReduceRelationshipChanged:
    def test_produces_relationship_fact(self):
        state = CoherenceState()
        event = {"type": "relationship_changed", "payload": {"npc_id": "guard", "target_id": "player", "relationship": 0.5}, "event_id": "e1", "tick": 1}
        mutations = reduce_relationship_changed(state, event)
        assert len(mutations) == 1
        assert mutations[0].data["predicate"] == "relationship:player"

    def test_empty_if_no_target(self):
        state = CoherenceState()
        event = {"type": "relationship_changed", "payload": {"npc_id": "guard"}, "event_id": "e1", "tick": 1}
        assert reduce_relationship_changed(state, event) == []


class TestReduceItemAcquired:
    def test_produces_owner_fact(self):
        state = CoherenceState()
        event = {"type": "item_acquired", "payload": {"actor_id": "player", "item_id": "sword"}, "event_id": "e1", "tick": 1}
        mutations = reduce_item_acquired(state, event)
        assert len(mutations) == 1
        assert mutations[0].data["predicate"] == "owner"
        assert mutations[0].data["value"] == "player"

    def test_empty_if_no_item(self):
        state = CoherenceState()
        event = {"type": "item_acquired", "payload": {"actor_id": "player"}, "event_id": "e1", "tick": 1}
        assert reduce_item_acquired(state, event) == []


class TestReduceItemLost:
    def test_produces_uncertain_assumption(self):
        state = CoherenceState()
        event = {"type": "item_lost", "payload": {"item_id": "shield"}, "event_id": "e1", "tick": 1}
        mutations = reduce_item_lost(state, event)
        assert len(mutations) == 1
        assert mutations[0].data["status"] == "uncertain"
        assert mutations[0].data["value"] is None

    def test_empty_if_no_item(self):
        state = CoherenceState()
        event = {"type": "item_lost", "payload": {}, "event_id": "e1", "tick": 1}
        assert reduce_item_lost(state, event) == []


class TestReduceThreadStarted:
    def test_produces_thread_mutation(self):
        state = CoherenceState()
        event = {"type": "quest_started", "payload": {"quest_id": "q1", "title": "Find the relic"}, "event_id": "e1", "tick": 1}
        mutations = reduce_thread_started(state, event)
        assert len(mutations) == 1
        assert mutations[0].action == "upsert_thread"
        assert mutations[0].data["thread_id"] == "q1"

    def test_fallback_thread_id(self):
        state = CoherenceState()
        event = {"type": "thread_started", "payload": {"title": "Mystery"}, "event_id": "e5", "tick": 1}
        mutations = reduce_thread_started(state, event)
        assert mutations[0].data["thread_id"] == "thread:e5"


class TestReduceThreadResolved:
    def test_produces_resolve_mutation(self):
        state = CoherenceState()
        event = {"type": "thread_resolved", "payload": {"thread_id": "q1"}, "event_id": "e1", "tick": 2}
        mutations = reduce_thread_resolved(state, event)
        assert len(mutations) == 1
        assert mutations[0].action == "resolve_thread"

    def test_empty_if_no_thread_id(self):
        state = CoherenceState()
        event = {"type": "thread_resolved", "payload": {}, "event_id": "e1", "tick": 1}
        assert reduce_thread_resolved(state, event) == []


class TestReduceCommitmentCreated:
    def test_produces_commitment(self):
        state = CoherenceState()
        event = {"type": "promise_made", "payload": {"actor_id": "player", "target_id": "guard", "text": "I will help"}, "event_id": "e1", "tick": 1}
        mutations = reduce_commitment_created(state, event)
        assert len(mutations) == 1
        assert mutations[0].action == "upsert_commitment"
        assert mutations[0].data["actor_id"] == "player"


class TestReduceCommitmentBroken:
    def test_produces_break_mutation(self):
        state = CoherenceState()
        event = {"type": "promise_broken", "payload": {"commitment_id": "c1"}, "event_id": "e1", "tick": 2}
        mutations = reduce_commitment_broken(state, event)
        assert len(mutations) == 1
        assert mutations[0].action == "break_commitment"

    def test_empty_if_no_commitment_id(self):
        state = CoherenceState()
        event = {"type": "promise_broken", "payload": {}, "event_id": "e1", "tick": 1}
        assert reduce_commitment_broken(state, event) == []


class TestReduceCharacterDeath:
    def test_produces_alive_false_fact(self):
        state = CoherenceState()
        event = {"type": "character_died", "payload": {"entity_id": "guard"}, "event_id": "e1", "tick": 1}
        mutations = reduce_character_death(state, event)
        assert len(mutations) == 1
        assert mutations[0].data["predicate"] == "alive"
        assert mutations[0].data["value"] is False

    def test_empty_if_no_entity(self):
        state = CoherenceState()
        event = {"type": "character_died", "payload": {}, "event_id": "e1", "tick": 1}
        assert reduce_character_death(state, event) == []


class TestReducerDispatch:
    def test_registered_event_types(self):
        expected = {
            "scene_started", "scene_generated", "npc_moved", "relationship_changed",
            "item_acquired", "item_lost", "quest_started", "thread_started",
            "quest_completed", "thread_resolved", "promise_made", "threat_made",
            "promise_broken", "character_died",
            # Phase 7.3 — Action-generated event types
            "thread_progressed", "npc_interaction_started",
            "scene_transition_requested", "recap_requested",
        }
        assert set(REDUCERS.keys()) == expected

    def test_unknown_event_returns_empty(self):
        state = CoherenceState()
        event = {"type": "unknown_event", "payload": {}, "event_id": "e1", "tick": 1}
        assert reduce_event(state, event) == []


# ---------------------------------------------------------------------------
# Contradiction Detector Tests
# ---------------------------------------------------------------------------

class TestContradictionDetector:
    def test_dead_actor_location_update(self):
        state = CoherenceState()
        state.stable_world_facts["guard:alive"] = FactRecord(
            fact_id="guard:alive", category="world", subject="guard",
            predicate="alive", value=False, authority="event_confirmed",
        )
        mutation = CoherenceMutation(
            action="upsert_fact", target="world",
            data={"subject": "guard", "predicate": "location", "value": "market", "fact_id": "guard:location"},
        )
        detector = ContradictionDetector()
        contradictions = detector.detect(state, [mutation], {"event_id": "e1", "tick": 2})
        assert len(contradictions) == 1
        assert contradictions[0].contradiction_type == "dead_actor_conflict"
        assert contradictions[0].severity == "high"

    def test_no_contradiction_for_living_actor(self):
        state = CoherenceState()
        mutation = CoherenceMutation(
            action="upsert_fact", target="world",
            data={"subject": "guard", "predicate": "location", "value": "market", "fact_id": "guard:location"},
        )
        detector = ContradictionDetector()
        contradictions = detector.detect(state, [mutation], {"event_id": "e1", "tick": 1})
        assert len(contradictions) == 0

    def test_location_conflict(self):
        state = CoherenceState()
        state.stable_world_facts["guard:location"] = FactRecord(
            fact_id="guard:location", category="world", subject="guard",
            predicate="location", value="gate", authority="event_confirmed",
        )
        mutation = CoherenceMutation(
            action="upsert_fact", target="world",
            data={"subject": "guard", "predicate": "location", "value": "market", "fact_id": "guard:location"},
        )
        detector = ContradictionDetector()
        contradictions = detector.detect(state, [mutation], {"event_id": "e1", "tick": 2})
        assert any(c.contradiction_type == "location_conflict" for c in contradictions)

    def test_inventory_conflict(self):
        state = CoherenceState()
        state.stable_world_facts["item:sword:owner"] = FactRecord(
            fact_id="item:sword:owner", category="world", subject="sword",
            predicate="owner", value="player", authority="event_confirmed",
        )
        mutation = CoherenceMutation(
            action="upsert_fact", target="world",
            data={"subject": "sword", "predicate": "owner", "value": "thief", "fact_id": "item:sword:owner"},
        )
        detector = ContradictionDetector()
        contradictions = detector.detect(state, [mutation], {"event_id": "e1", "tick": 2})
        assert any(c.contradiction_type == "inventory_conflict" for c in contradictions)

    def test_thread_resolution_conflict(self):
        state = CoherenceState()
        # Thread t1 doesn't exist in unresolved_threads
        mutation = CoherenceMutation(
            action="resolve_thread", target="thread",
            data={"thread_id": "t1"},
        )
        detector = ContradictionDetector()
        contradictions = detector.detect(state, [mutation], {"event_id": "e1", "tick": 2})
        assert any(c.contradiction_type == "thread_resolution_conflict" for c in contradictions)

    def test_no_thread_conflict_when_thread_exists(self):
        state = CoherenceState()
        state.unresolved_threads["t1"] = ThreadRecord(thread_id="t1", title="Quest")
        mutation = CoherenceMutation(
            action="resolve_thread", target="thread",
            data={"thread_id": "t1"},
        )
        detector = ContradictionDetector()
        contradictions = detector.detect(state, [mutation], {"event_id": "e1", "tick": 2})
        assert not any(c.contradiction_type == "thread_resolution_conflict" for c in contradictions)

    def test_no_event_id_graceful(self):
        """Detector should handle None event gracefully."""
        state = CoherenceState()
        state.stable_world_facts["guard:alive"] = FactRecord(
            fact_id="guard:alive", category="world", subject="guard",
            predicate="alive", value=False, authority="event_confirmed",
        )
        mutation = CoherenceMutation(
            action="upsert_fact", target="world",
            data={"subject": "guard", "predicate": "location", "value": "market", "fact_id": "guard:location"},
        )
        detector = ContradictionDetector()
        contradictions = detector.detect(state, [mutation], None)
        assert len(contradictions) == 1


# ---------------------------------------------------------------------------
# Query API Tests
# ---------------------------------------------------------------------------

class TestCoherenceQueryAPI:
    def test_get_scene_summary_empty(self):
        state = CoherenceState()
        api = CoherenceQueryAPI(state)
        summary = api.get_scene_summary()
        assert summary["location"] is None
        assert summary["summary"] == ""

    def test_get_scene_summary_with_data(self):
        state = CoherenceState()
        state.scene_facts["scene:location"] = FactRecord(
            fact_id="scene:location", category="scene", subject="scene",
            predicate="location", value="tavern",
        )
        state.continuity_anchors.append(SceneAnchor(
            anchor_id="a1", tick=1, location="tavern",
            summary="A busy tavern", present_actors=["player", "barkeep"],
        ))
        api = CoherenceQueryAPI(state)
        summary = api.get_scene_summary()
        assert summary["location"] == "tavern"
        assert summary["summary"] == "A busy tavern"
        assert "player" in summary["present_actors"]

    def test_get_active_tensions_empty(self):
        state = CoherenceState()
        api = CoherenceQueryAPI(state)
        assert api.get_active_tensions() == []

    def test_get_active_tensions(self):
        state = CoherenceState()
        state.continuity_anchors.append(SceneAnchor(
            anchor_id="a1", tick=1, location="gate",
            active_tensions=["bandit attack"],
        ))
        api = CoherenceQueryAPI(state)
        tensions = api.get_active_tensions()
        assert len(tensions) == 1
        assert tensions[0]["text"] == "bandit attack"

    def test_get_unresolved_threads(self):
        state = CoherenceState()
        state.unresolved_threads["t1"] = ThreadRecord(thread_id="t1", title="Find the relic")
        state.unresolved_threads["t2"] = ThreadRecord(thread_id="t2", title="Resolved", status="resolved")
        api = CoherenceQueryAPI(state)
        threads = api.get_unresolved_threads()
        assert len(threads) == 1
        assert threads[0]["thread_id"] == "t1"

    def test_get_actor_commitments(self):
        state = CoherenceState()
        state.player_commitments["c1"] = CommitmentRecord(
            commitment_id="c1", actor_id="player", target_id="guard",
            kind="promise", text="I'll help",
        )
        state.npc_commitments["c2"] = CommitmentRecord(
            commitment_id="c2", actor_id="guard", target_id="player",
            kind="threat", text="Watch out", status="broken",
        )
        api = CoherenceQueryAPI(state)
        commitments = api.get_actor_commitments("player")
        assert len(commitments) == 1
        assert commitments[0]["commitment_id"] == "c1"

    def test_get_known_facts(self):
        state = CoherenceState()
        state.stable_world_facts["guard:location"] = FactRecord(
            fact_id="guard:location", category="world", subject="guard",
            predicate="location", value="gate",
        )
        state.scene_facts["scene:location"] = FactRecord(
            fact_id="scene:location", category="scene", subject="scene",
            predicate="location", value="market",
        )
        api = CoherenceQueryAPI(state)
        result = api.get_known_facts("guard")
        assert result["entity_id"] == "guard"
        assert len(result["facts"]) == 1

    def test_get_recent_consequences(self):
        state = CoherenceState()
        for i in range(15):
            state.recent_changes.append(ConsequenceRecord(
                consequence_id=f"c{i}", event_id=f"e{i}", tick=i, summary=f"Event {i}",
            ))
        api = CoherenceQueryAPI(state)
        recent = api.get_recent_consequences(limit=5)
        assert len(recent) == 5

    def test_get_last_good_anchor_empty(self):
        state = CoherenceState()
        api = CoherenceQueryAPI(state)
        assert api.get_last_good_anchor() is None

    def test_get_last_good_anchor(self):
        state = CoherenceState()
        state.continuity_anchors.append(SceneAnchor(anchor_id="a1", tick=1, location="gate"))
        state.continuity_anchors.append(SceneAnchor(anchor_id="a2", tick=2, location="market"))
        api = CoherenceQueryAPI(state)
        anchor = api.get_last_good_anchor()
        assert anchor["anchor_id"] == "a2"

    def test_get_entity_view(self):
        state = CoherenceState()
        state.stable_world_facts["guard:location"] = FactRecord(
            fact_id="guard:location", category="world", subject="guard",
            predicate="location", value="gate",
        )
        state.npc_commitments["c1"] = CommitmentRecord(
            commitment_id="c1", actor_id="guard", target_id="player",
            kind="threat", text="Watch out",
        )
        api = CoherenceQueryAPI(state)
        view = api.get_entity_view("guard")
        assert view["entity_id"] == "guard"
        assert len(view["facts"]) == 1
        assert len(view["commitments"]) == 1


# ---------------------------------------------------------------------------
# CoherenceCore Tests
# ---------------------------------------------------------------------------

class TestCoherenceCore:
    def test_initial_state(self):
        core = CoherenceCore()
        assert core.mode == "live"
        state = core.get_state()
        assert isinstance(state, CoherenceState)

    def test_set_mode(self):
        core = CoherenceCore()
        core.set_mode("replay")
        assert core.mode == "replay"

    def test_apply_event_character_death(self):
        core = CoherenceCore()
        result = core.apply_event(
            Event("character_died", {"entity_id": "guard"}, source="test", event_id="e1", tick=1)
        )
        assert result.events_applied == 1
        facts = core.get_known_facts("guard")["facts"]
        alive_facts = [f for f in facts if f["predicate"] == "alive"]
        assert alive_facts
        assert alive_facts[0]["value"] is False

    def test_apply_event_npc_moved(self):
        core = CoherenceCore()
        core.apply_event(
            Event("npc_moved", {"npc_id": "guard", "location": "market"}, source="test", event_id="e1", tick=1)
        )
        facts = core.get_known_facts("guard")["facts"]
        loc = [f for f in facts if f["predicate"] == "location"]
        assert loc[0]["value"] == "market"

    def test_apply_events_batch(self):
        core = CoherenceCore()
        events = [
            Event("npc_moved", {"npc_id": "guard", "location": "market"}, source="test", event_id="e1", tick=1),
            Event("quest_started", {"quest_id": "q1", "title": "Find relic"}, source="test", event_id="e2", tick=1),
        ]
        result = core.apply_events(events)
        assert result.events_applied == 2
        assert len(core.get_unresolved_threads()) == 1

    def test_authority_prevents_overwrite(self):
        core = CoherenceCore()
        core.insert_fact(FactRecord(
            fact_id="guard:location", category="world", subject="guard",
            predicate="location", value="gate", authority="creator_canon",
        ))
        core.apply_event(
            Event("npc_moved", {"npc_id": "guard", "location": "tower"}, source="test", event_id="e2", tick=2)
        )
        facts = core.get_known_facts("guard")["facts"]
        loc = [f for f in facts if f["predicate"] == "location"]
        assert loc[0]["value"] == "gate"  # creator_canon > event_confirmed

    def test_thread_lifecycle(self):
        core = CoherenceCore()
        core.apply_event(
            Event("quest_started", {"quest_id": "q1", "title": "Find relic"}, source="test", event_id="e1", tick=1)
        )
        assert len(core.get_unresolved_threads()) == 1

        core.apply_event(
            Event("thread_resolved", {"thread_id": "q1"}, source="test", event_id="e2", tick=2)
        )
        unresolved = [t for t in core.get_unresolved_threads() if t["status"] != "resolved"]
        assert unresolved == []

    def test_commitment_lifecycle(self):
        core = CoherenceCore()
        core.apply_event(
            Event("promise_made", {"actor_id": "player", "target_id": "guard", "text": "I'll help"}, source="test", event_id="e1", tick=1)
        )
        commitments = core.get_actor_commitments("player")
        assert len(commitments) == 1

        core.apply_event(
            Event("promise_broken", {"commitment_id": commitments[0]["commitment_id"]}, source="test", event_id="e2", tick=2)
        )
        commitments = core.get_actor_commitments("player")
        assert len(commitments) == 0  # broken commitments are not active

    def test_scene_summary(self):
        core = CoherenceCore()
        core.apply_event(
            Event("scene_started", {"location": "market", "present_actors": ["player"]}, source="test", event_id="e1", tick=1)
        )
        summary = core.get_scene_summary()
        assert summary["location"] == "market"

    def test_contradiction_detection(self):
        core = CoherenceCore()
        core.apply_event(
            Event("character_died", {"entity_id": "guard"}, source="test", event_id="e1", tick=1)
        )
        result = core.apply_event(
            Event("npc_moved", {"npc_id": "guard", "location": "market"}, source="test", event_id="e2", tick=2)
        )
        assert len(result.contradictions) > 0
        assert result.contradictions[0].contradiction_type == "dead_actor_conflict"

    def test_serialize_deserialize(self):
        core = CoherenceCore()
        core.apply_event(
            Event("npc_moved", {"npc_id": "guard", "location": "market"}, source="test", event_id="e1", tick=1)
        )
        core.apply_event(
            Event("quest_started", {"quest_id": "q1", "title": "Find relic"}, source="test", event_id="e2", tick=2)
        )
        data = core.serialize_state()
        new_core = CoherenceCore()
        new_core.deserialize_state(data)
        assert new_core.get_known_facts("guard")["facts"][0]["value"] == "market"
        assert len(new_core.get_unresolved_threads()) == 1

    def test_snapshot_aliases(self):
        core = CoherenceCore()
        core.apply_event(
            Event("scene_started", {"location": "gate"}, source="test", event_id="e1", tick=1)
        )
        data = core.serialize()
        new_core = CoherenceCore()
        new_core.deserialize(data)
        assert new_core.get_scene_summary()["location"] == "gate"

    def test_anchor_cap(self):
        core = CoherenceCore()
        for i in range(60):
            core.push_anchor(SceneAnchor(anchor_id=f"a{i}", tick=i, location=f"loc{i}"))
        assert len(core.state.continuity_anchors) == 50

    def test_contradiction_cap(self):
        core = CoherenceCore()
        for i in range(210):
            core.record_contradictions([ContradictionRecord(
                contradiction_id=f"ct{i}", contradiction_type="test", severity="info", message=f"test {i}",
            )])
        assert len(core.state.contradictions) == 200

    def test_recent_changes_cap(self):
        core = CoherenceCore()
        for i in range(110):
            core.state.recent_changes.append(ConsequenceRecord(
                consequence_id=f"c{i}", event_id=f"e{i}", tick=i, summary=f"Event {i}",
            ))
        # Trigger cap via apply_mutation
        core._apply_mutation(CoherenceMutation(
            action="record_consequence",
            target="consequence",
            data={"consequence_id": "final", "event_id": "efinal", "tick": 999, "summary": "final"},
        ))
        assert len(core.state.recent_changes) <= 100

    def test_remove_fact(self):
        core = CoherenceCore()
        core.insert_fact(FactRecord(
            fact_id="test:fact", category="world", subject="test",
            predicate="value", value=42, authority="runtime",
        ))
        core.remove_fact("test:fact")
        assert core.get_known_facts("test")["facts"] == []


class TestAuthorityRank:
    def test_ranks_ordered(self):
        assert AUTHORITY_RANK["creator_canon"] > AUTHORITY_RANK["event_confirmed"]
        assert AUTHORITY_RANK["event_confirmed"] > AUTHORITY_RANK["runtime"]
        assert AUTHORITY_RANK["runtime"] > AUTHORITY_RANK["assumption"]

    def test_all_authorities_present(self):
        expected = {"creator_canon", "engine_confirmed", "event_confirmed",
                    "player_commitment", "npc_commitment", "runtime", "inferred", "assumption"}
        assert set(AUTHORITY_RANK.keys()) == expected