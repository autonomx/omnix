"""Phase 7.6 — Unit Tests for Persistent Social State.

Covers:
- Model roundtrip serialization
- Reputation edge adjustments and clamping
- Relationship tracker adjustments and clamping
- Rumor seed/spread progression
- Alliance strength → status mapping
- Social reducers update state deterministically
- Query API returns stable dict shapes
"""

from __future__ import annotations

from app.rpg.social_state.alliance_tracker import AllianceTracker
from app.rpg.social_state.core import SocialStateCore
from app.rpg.social_state.models import (
    AllianceRecord,
    RelationshipStateRecord,
    ReputationEdge,
    RumorRecord,
    SocialState,
)
from app.rpg.social_state.query import SocialStateQuery
from app.rpg.social_state.relationship_tracker import RelationshipTracker
from app.rpg.social_state.reputation_graph import ReputationGraph
from app.rpg.social_state.rumor_log import RumorLog

# ---------------------------------------------------------------
# Model roundtrip tests
# ---------------------------------------------------------------


class TestReputationEdgeRoundtrip:
    def test_reputation_edge_roundtrip(self):
        edge = ReputationEdge(
            source_id="npc_1",
            target_id="player",
            score=0.5,
            edge_type="reputation",
            last_event_id="evt_1",
            metadata={"reason": "helped"},
        )
        d = edge.to_dict()
        restored = ReputationEdge.from_dict(d)
        assert restored.source_id == "npc_1"
        assert restored.target_id == "player"
        assert restored.score == 0.5
        assert restored.edge_type == "reputation"
        assert restored.last_event_id == "evt_1"
        assert restored.metadata == {"reason": "helped"}

    def test_reputation_edge_defaults(self):
        edge = ReputationEdge(source_id="a", target_id="b")
        d = edge.to_dict()
        assert d["score"] == 0.0
        assert d["edge_type"] == "reputation"
        assert d["last_event_id"] is None
        assert d["metadata"] == {}


class TestRelationshipStateRecordRoundtrip:
    def test_relationship_state_record_roundtrip(self):
        record = RelationshipStateRecord(
            relationship_id="rel:npc_1:player",
            source_id="npc_1",
            target_id="player",
            trust=0.3,
            fear=0.1,
            hostility=-0.2,
            respect=0.5,
            last_event_id="evt_2",
            metadata={"note": "test"},
        )
        d = record.to_dict()
        restored = RelationshipStateRecord.from_dict(d)
        assert restored.relationship_id == "rel:npc_1:player"
        assert restored.trust == 0.3
        assert restored.fear == 0.1
        assert restored.hostility == -0.2
        assert restored.respect == 0.5

    def test_relationship_state_record_defaults(self):
        record = RelationshipStateRecord(
            relationship_id="r1", source_id="a", target_id="b"
        )
        assert record.trust == 0.0
        assert record.fear == 0.0
        assert record.hostility == 0.0
        assert record.respect == 0.0


class TestRumorRecordRoundtrip:
    def test_rumor_record_roundtrip(self):
        rumor = RumorRecord(
            rumor_id="rumor_1",
            source_npc_id="npc_1",
            subject_id="player",
            rumor_type="suspicion",
            summary="Player was seen near the vault",
            location="market",
            spread_level=2,
            active=True,
            last_event_id="evt_3",
            metadata={"severity": "medium"},
        )
        d = rumor.to_dict()
        restored = RumorRecord.from_dict(d)
        assert restored.rumor_id == "rumor_1"
        assert restored.source_npc_id == "npc_1"
        assert restored.rumor_type == "suspicion"
        assert restored.spread_level == 2
        assert restored.active is True

    def test_rumor_record_defaults(self):
        rumor = RumorRecord(
            rumor_id="r1",
            source_npc_id=None,
            subject_id=None,
            rumor_type="general",
            summary="A rumor",
        )
        assert rumor.spread_level == 0
        assert rumor.active is True
        assert rumor.location is None


class TestAllianceRecordRoundtrip:
    def test_alliance_record_roundtrip(self):
        alliance = AllianceRecord(
            alliance_id="alliance:a:b",
            entity_a="faction_a",
            entity_b="faction_b",
            strength=0.7,
            status="allied",
            last_event_id="evt_4",
            metadata={"treaty": True},
        )
        d = alliance.to_dict()
        restored = AllianceRecord.from_dict(d)
        assert restored.alliance_id == "alliance:a:b"
        assert restored.strength == 0.7
        assert restored.status == "allied"

    def test_alliance_record_defaults(self):
        alliance = AllianceRecord(
            alliance_id="a1", entity_a="a", entity_b="b"
        )
        assert alliance.strength == 0.0
        assert alliance.status == "neutral"


class TestSocialStateRoundtrip:
    def test_social_state_roundtrip(self):
        state = SocialState(
            reputation_edges={
                "rep:a:b": ReputationEdge(source_id="a", target_id="b", score=0.5)
            },
            relationships={
                "rel:a:b": RelationshipStateRecord(
                    relationship_id="rel:a:b",
                    source_id="a",
                    target_id="b",
                    trust=0.3,
                )
            },
            rumors={
                "r1": RumorRecord(
                    rumor_id="r1",
                    source_npc_id="a",
                    subject_id="b",
                    rumor_type="gossip",
                    summary="test",
                )
            },
            alliances={
                "alliance:a:b": AllianceRecord(
                    alliance_id="alliance:a:b",
                    entity_a="a",
                    entity_b="b",
                    strength=0.6,
                    status="allied",
                )
            },
        )
        d = state.to_dict()
        restored = SocialState.from_dict(d)
        assert "rep:a:b" in restored.reputation_edges
        assert restored.reputation_edges["rep:a:b"].score == 0.5
        assert "rel:a:b" in restored.relationships
        assert restored.relationships["rel:a:b"].trust == 0.3
        assert "r1" in restored.rumors
        assert restored.rumors["r1"].rumor_type == "gossip"
        assert "alliance:a:b" in restored.alliances
        assert restored.alliances["alliance:a:b"].status == "allied"

    def test_empty_social_state_roundtrip(self):
        state = SocialState()
        d = state.to_dict()
        restored = SocialState.from_dict(d)
        assert restored.reputation_edges == {}
        assert restored.relationships == {}
        assert restored.rumors == {}
        assert restored.alliances == {}


# ---------------------------------------------------------------
# Reputation graph tests
# ---------------------------------------------------------------


class TestReputationGraph:
    def test_reputation_graph_adjust_score_clamps_range(self):
        graph = ReputationGraph()
        state = SocialState()

        # Adjust to positive
        edge = graph.adjust_score(state, "a", "b", 0.5)
        assert edge.score == 0.5

        # Clamp at 1.0
        edge = graph.adjust_score(state, "a", "b", 0.8)
        assert edge.score == 1.0

        # Adjust negative
        edge = graph.adjust_score(state, "a", "b", -2.5)
        assert edge.score == -1.0

    def test_reputation_graph_get_edge_none(self):
        graph = ReputationGraph()
        state = SocialState()
        assert graph.get_edge(state, "a", "b") is None

    def test_reputation_graph_upsert_and_get(self):
        graph = ReputationGraph()
        state = SocialState()
        edge = ReputationEdge(source_id="a", target_id="b", score=0.3)
        graph.upsert_edge(state, edge)
        retrieved = graph.get_edge(state, "a", "b")
        assert retrieved is not None
        assert retrieved.score == 0.3

    def test_reputation_graph_adjust_sets_event_id(self):
        graph = ReputationGraph()
        state = SocialState()
        edge = graph.adjust_score(state, "a", "b", 0.1, event_id="evt_1")
        assert edge.last_event_id == "evt_1"

    def test_reputation_graph_adjust_merges_metadata(self):
        graph = ReputationGraph()
        state = SocialState()
        graph.adjust_score(state, "a", "b", 0.1, metadata={"reason": "helped"})
        graph.adjust_score(state, "a", "b", 0.1, metadata={"context": "quest"})
        edge = graph.get_edge(state, "a", "b")
        assert edge.metadata["reason"] == "helped"
        assert edge.metadata["context"] == "quest"


# ---------------------------------------------------------------
# Relationship tracker tests
# ---------------------------------------------------------------


class TestRelationshipTracker:
    def test_relationship_tracker_adjust_clamps_values(self):
        tracker = RelationshipTracker()
        state = SocialState()

        record = tracker.adjust(state, "npc_1", "player", trust=0.5, fear=0.5)
        assert record.trust == 0.5
        assert record.fear == 0.5

        # Clamp at 1.0
        record = tracker.adjust(state, "npc_1", "player", trust=0.8, fear=0.8)
        assert record.trust == 1.0
        assert record.fear == 1.0

        # Clamp at -1.0
        record = tracker.adjust(state, "npc_1", "player", trust=-3.0)
        assert record.trust == -1.0

    def test_relationship_tracker_get_none(self):
        tracker = RelationshipTracker()
        state = SocialState()
        assert tracker.get(state, "a", "b") is None

    def test_relationship_tracker_upsert_and_get(self):
        tracker = RelationshipTracker()
        state = SocialState()
        record = RelationshipStateRecord(
            relationship_id="rel:a:b",
            source_id="a",
            target_id="b",
            trust=0.4,
        )
        tracker.upsert(state, record)
        retrieved = tracker.get(state, "a", "b")
        assert retrieved is not None
        assert retrieved.trust == 0.4

    def test_relationship_tracker_adjust_all_metrics(self):
        tracker = RelationshipTracker()
        state = SocialState()
        record = tracker.adjust(
            state, "a", "b",
            trust=0.1, fear=0.2, hostility=0.3, respect=0.4,
            event_id="evt_1",
        )
        assert record.trust == 0.1
        assert record.fear == 0.2
        assert record.hostility == 0.3
        assert record.respect == 0.4
        assert record.last_event_id == "evt_1"

    def test_relationship_tracker_adjust_accumulates(self):
        tracker = RelationshipTracker()
        state = SocialState()
        tracker.adjust(state, "a", "b", trust=0.3)
        tracker.adjust(state, "a", "b", trust=0.2)
        record = tracker.get(state, "a", "b")
        assert abs(record.trust - 0.5) < 1e-9


# ---------------------------------------------------------------
# Rumor log tests
# ---------------------------------------------------------------


class TestRumorLog:
    def test_rumor_log_seed_and_increase_spread(self):
        log = RumorLog()
        state = SocialState()

        rumor = log.seed_rumor(
            state,
            rumor_id="rumor_1",
            source_npc_id="npc_1",
            subject_id="player",
            rumor_type="suspicion",
            summary="Suspicious activity",
            location="market",
            event_id="evt_1",
        )
        assert rumor.spread_level == 0
        assert rumor.active is True

        updated = log.increase_spread(state, "rumor_1", amount=2)
        assert updated.spread_level == 2

        updated = log.increase_spread(state, "rumor_1")
        assert updated.spread_level == 3

    def test_rumor_log_get_none(self):
        log = RumorLog()
        state = SocialState()
        assert log.get(state, "nonexistent") is None

    def test_rumor_log_deactivate(self):
        log = RumorLog()
        state = SocialState()
        log.seed_rumor(
            state,
            rumor_id="r1",
            source_npc_id=None,
            subject_id=None,
            rumor_type="gossip",
            summary="test",
            location=None,
        )
        deactivated = log.deactivate(state, "r1", event_id="evt_2")
        assert deactivated is not None
        assert deactivated.active is False
        assert deactivated.last_event_id == "evt_2"

    def test_rumor_log_deactivate_nonexistent(self):
        log = RumorLog()
        state = SocialState()
        assert log.deactivate(state, "nonexistent") is None

    def test_rumor_log_increase_spread_nonexistent(self):
        log = RumorLog()
        state = SocialState()
        assert log.increase_spread(state, "nonexistent") is None

    def test_rumor_log_upsert(self):
        log = RumorLog()
        state = SocialState()
        rumor = RumorRecord(
            rumor_id="r1",
            source_npc_id="npc_1",
            subject_id="player",
            rumor_type="gossip",
            summary="test",
        )
        log.upsert(state, rumor)
        assert log.get(state, "r1") is not None


# ---------------------------------------------------------------
# Alliance tracker tests
# ---------------------------------------------------------------


class TestAllianceTracker:
    def test_alliance_tracker_status_updates_from_strength(self):
        tracker = AllianceTracker()
        state = SocialState()

        # Allied
        record = tracker.adjust_strength(state, "faction_a", "faction_b", 0.7)
        assert record.status == "allied"

        # Bring down to hostile
        record = tracker.adjust_strength(state, "faction_a", "faction_b", -2.0)
        assert record.status == "hostile"

    def test_alliance_tracker_status_thresholds(self):
        tracker = AllianceTracker()

        assert tracker._status_from_strength(1.0) == "allied"
        assert tracker._status_from_strength(0.6) == "allied"
        assert tracker._status_from_strength(0.4) == "friendly"
        assert tracker._status_from_strength(0.2) == "friendly"
        assert tracker._status_from_strength(0.0) == "neutral"
        assert tracker._status_from_strength(-0.1) == "neutral"
        assert tracker._status_from_strength(-0.3) == "tense"
        assert tracker._status_from_strength(-0.5) == "tense"
        assert tracker._status_from_strength(-0.6) == "hostile"
        assert tracker._status_from_strength(-1.0) == "hostile"

    def test_alliance_tracker_symmetric_id(self):
        tracker = AllianceTracker()
        assert tracker._alliance_id("a", "b") == tracker._alliance_id("b", "a")

    def test_alliance_tracker_get_none(self):
        tracker = AllianceTracker()
        state = SocialState()
        assert tracker.get(state, "a", "b") is None

    def test_alliance_tracker_clamps_strength(self):
        tracker = AllianceTracker()
        state = SocialState()
        record = tracker.adjust_strength(state, "a", "b", 2.0)
        assert record.strength == 1.0
        record = tracker.adjust_strength(state, "a", "b", -5.0)
        assert record.strength == -1.0


# ---------------------------------------------------------------
# Social state core + reducers tests
# ---------------------------------------------------------------


class TestSocialStateCore:
    def test_social_state_core_apply_event_updates_relationships(self):
        core = SocialStateCore()

        event = {
            "type": "npc_response_agreed",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        }
        core.apply_event(event)

        state = core.get_state()
        # Check that a relationship was created
        assert len(state.relationships) > 0
        rel = list(state.relationships.values())[0]
        assert rel.trust > 0.0
        assert rel.respect > 0.0

    def test_social_state_core_apply_event_refused(self):
        core = SocialStateCore()
        event = {
            "type": "npc_response_refused",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        }
        core.apply_event(event)
        state = core.get_state()
        rel = list(state.relationships.values())[0]
        assert rel.trust < 0.0
        assert rel.hostility > 0.0

    def test_social_state_core_apply_event_threatened(self):
        core = SocialStateCore()
        event = {
            "type": "npc_response_threatened",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        }
        core.apply_event(event)
        state = core.get_state()
        rel = list(state.relationships.values())[0]
        assert rel.fear > 0.0
        assert rel.hostility > 0.0
        # Also check reputation
        assert len(state.reputation_edges) > 0

    def test_social_state_core_apply_events_multiple(self):
        core = SocialStateCore()
        events = [
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
        ]
        core.apply_events(events)
        state = core.get_state()
        rel = list(state.relationships.values())[0]
        assert abs(rel.trust - 0.2) < 1e-9

    def test_social_state_core_apply_rumor_seeded(self):
        core = SocialStateCore()
        event = {
            "type": "rumor_seeded",
            "payload": {
                "rumor_id": "rumor_1",
                "source_npc_id": "npc_1",
                "subject_id": "player",
                "rumor_type": "suspicion",
                "summary": "Suspicious activity",
                "location": "market",
            },
        }
        core.apply_event(event)
        state = core.get_state()
        assert "rumor_1" in state.rumors
        assert state.rumors["rumor_1"].active is True

    def test_social_state_core_apply_secondary_supported(self):
        core = SocialStateCore()
        event = {
            "type": "npc_secondary_supported",
            "payload": {"npc_id": "npc_2", "primary_npc_id": "npc_1"},
        }
        core.apply_event(event)
        state = core.get_state()
        assert len(state.alliances) > 0

    def test_social_state_core_apply_secondary_opposed(self):
        core = SocialStateCore()
        event = {
            "type": "npc_secondary_opposed",
            "payload": {"npc_id": "npc_2", "primary_npc_id": "npc_1"},
        }
        core.apply_event(event)
        state = core.get_state()
        assert len(state.alliances) > 0
        alliance = list(state.alliances.values())[0]
        assert alliance.strength < 0.0

    def test_social_state_core_apply_action_blocked(self):
        core = SocialStateCore()
        event = {"type": "action_blocked", "payload": {}}
        core.apply_event(event)
        state = core.get_state()
        # action_blocked should not create any social state
        assert len(state.relationships) == 0
        assert len(state.reputation_edges) == 0

    def test_social_state_core_apply_unknown_event(self):
        core = SocialStateCore()
        event = {"type": "unknown_event_type", "payload": {}}
        core.apply_event(event)
        state = core.get_state()
        # Unknown events should be ignored
        assert len(state.relationships) == 0

    def test_social_state_core_apply_delayed(self):
        core = SocialStateCore()
        event = {
            "type": "npc_response_delayed",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        }
        core.apply_event(event)
        state = core.get_state()
        rel = list(state.relationships.values())[0]
        assert rel.trust == 0.0  # delayed doesn't change trust
        assert rel.metadata.get("delayed") is True

    def test_social_state_core_apply_redirected(self):
        core = SocialStateCore()
        event = {
            "type": "npc_response_redirected",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        }
        core.apply_event(event)
        state = core.get_state()
        rel = list(state.relationships.values())[0]
        assert rel.trust < 0.0

    def test_social_state_core_set_mode(self):
        core = SocialStateCore()
        core.set_mode("replay")
        assert core._mode == "replay"

    def test_social_state_core_serialize_deserialize(self):
        core = SocialStateCore()
        core.apply_event({
            "type": "npc_response_agreed",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        })
        data = core.serialize_state()
        core2 = SocialStateCore()
        core2.deserialize_state(data)
        state = core2.get_state()
        assert len(state.relationships) > 0


# ---------------------------------------------------------------
# Query API tests
# ---------------------------------------------------------------


class TestSocialStateQuery:
    def test_social_state_query_build_npc_social_view_returns_stable_shape(self):
        query = SocialStateQuery()
        state = SocialState()
        view = query.build_npc_social_view(state, "npc_1", "player")
        assert "npc_id" in view
        assert "target_id" in view
        assert "relationship" in view
        assert "reputation" in view
        assert "active_rumors" in view
        assert view["npc_id"] == "npc_1"
        assert view["target_id"] == "player"

    def test_social_state_query_get_relationship_none(self):
        query = SocialStateQuery()
        state = SocialState()
        assert query.get_relationship(state, "a", "b") is None

    def test_social_state_query_get_reputation_none(self):
        query = SocialStateQuery()
        state = SocialState()
        assert query.get_reputation(state, "a", "b") is None

    def test_social_state_query_get_alliance_none(self):
        query = SocialStateQuery()
        state = SocialState()
        assert query.get_alliance(state, "a", "b") is None

    def test_social_state_query_get_active_rumors_empty(self):
        query = SocialStateQuery()
        state = SocialState()
        assert query.get_active_rumors_for_subject(state, "player") == []

    def test_social_state_query_get_active_rumors(self):
        query = SocialStateQuery()
        state = SocialState()
        state.rumors["r1"] = RumorRecord(
            rumor_id="r1",
            source_npc_id="npc_1",
            subject_id="player",
            rumor_type="gossip",
            summary="test",
            active=True,
        )
        state.rumors["r2"] = RumorRecord(
            rumor_id="r2",
            source_npc_id="npc_2",
            subject_id="player",
            rumor_type="suspicion",
            summary="test2",
            active=False,
        )
        active = query.get_active_rumors_for_subject(state, "player")
        assert len(active) == 1
        assert active[0]["rumor_id"] == "r1"

    def test_social_state_query_with_populated_state(self):
        core = SocialStateCore()
        core.apply_event({
            "type": "npc_response_agreed",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        })
        query = core.get_query()
        state = core.get_state()

        view = query.build_npc_social_view(state, "npc_1", "player")
        assert view["relationship"] is not None
        assert view["relationship"]["trust"] > 0.0
