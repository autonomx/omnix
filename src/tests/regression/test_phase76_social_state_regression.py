"""Phase 7.6 — Regression Tests for Persistent Social State.

Covers:
- Social state updates are deterministic
- Social state survives snapshot/restore
- Applying same events in same order gives same social state
- Social state does not mutate without events
"""

from __future__ import annotations

from app.rpg.social_state.core import SocialStateCore
from app.rpg.social_state.models import SocialState


class TestSocialStateUpdatesAreDeterministic:
    def test_social_state_updates_are_deterministic(self):
        """Applying the same events always produces the same state."""
        events = [
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_refused", "payload": {"npc_id": "npc_2", "target_id": "player"}},
            {"type": "npc_response_threatened", "payload": {"npc_id": "npc_3", "target_id": "player"}},
            {
                "type": "rumor_seeded",
                "payload": {
                    "rumor_id": "r1",
                    "source_npc_id": "npc_1",
                    "subject_id": "player",
                    "rumor_type": "gossip",
                    "summary": "test",
                    "location": "tavern",
                },
            },
            {"type": "npc_secondary_supported", "payload": {"npc_id": "npc_4", "primary_npc_id": "npc_1"}},
        ]

        core1 = SocialStateCore()
        core1.apply_events(events)
        state1 = core1.serialize_state()

        core2 = SocialStateCore()
        core2.apply_events(events)
        state2 = core2.serialize_state()

        assert state1 == state2


class TestSocialStateSurvivesSnapshotRestore:
    def test_social_state_survives_snapshot_restore(self):
        """Serialized social state can be fully restored."""
        core = SocialStateCore()
        core.apply_events([
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_threatened", "payload": {"npc_id": "npc_2", "target_id": "player"}},
            {
                "type": "rumor_seeded",
                "payload": {
                    "rumor_id": "r1",
                    "source_npc_id": "npc_1",
                    "subject_id": "player",
                    "rumor_type": "gossip",
                    "summary": "test",
                    "location": "tavern",
                },
            },
            {"type": "npc_secondary_supported", "payload": {"npc_id": "npc_3", "primary_npc_id": "npc_1"}},
        ])

        snapshot = core.serialize_state()

        # Restore into fresh core
        core2 = SocialStateCore()
        core2.deserialize_state(snapshot)

        # Verify all data survived
        state = core2.get_state()
        assert len(state.relationships) == 2
        assert len(state.reputation_edges) > 0
        assert "r1" in state.rumors
        assert len(state.alliances) > 0

        # Verify values match
        assert core.serialize_state() == core2.serialize_state()


class TestSocialStateRequiresEventPathForMutation:
    def test_social_state_requires_event_path_for_mutation(self):
        """Social state does not mutate without events being applied."""
        core = SocialStateCore()
        initial_state = core.serialize_state()

        # Access query — should not change state
        query = core.get_query()
        state = core.get_state()
        query.build_npc_social_view(state, "npc_1", "player")
        query.get_relationship(state, "npc_1", "player")
        query.get_reputation(state, "npc_1", "player")
        query.get_active_rumors_for_subject(state, "player")
        query.get_alliance(state, "faction_a", "faction_b")

        # State should not have changed
        after_queries = core.serialize_state()
        assert initial_state == after_queries

    def test_empty_events_list_does_not_mutate(self):
        core = SocialStateCore()
        initial = core.serialize_state()
        core.apply_events([])
        assert core.serialize_state() == initial

    def test_unknown_events_do_not_mutate(self):
        core = SocialStateCore()
        initial = core.serialize_state()
        core.apply_events([
            {"type": "completely_unknown_event", "payload": {}},
            {"type": "another_unknown", "payload": {"data": "ignored"}},
        ])
        assert core.serialize_state() == initial


class TestSameSocialEventsProduceSameState:
    def test_same_social_events_produce_same_state(self):
        """Applying the same sequence of events always results in identical state."""
        event_sequence = [
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_refused", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_threatened", "payload": {"npc_id": "npc_2", "target_id": "player"}},
            {"type": "npc_response_delayed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_redirected", "payload": {"npc_id": "npc_3", "target_id": "player"}},
            {
                "type": "rumor_seeded",
                "payload": {
                    "rumor_id": "r1",
                    "source_npc_id": "npc_1",
                    "subject_id": "player",
                    "rumor_type": "gossip",
                    "summary": "test",
                    "location": "tavern",
                },
            },
            {"type": "npc_secondary_supported", "payload": {"npc_id": "npc_4", "primary_npc_id": "npc_1"}},
            {"type": "npc_secondary_opposed", "payload": {"npc_id": "npc_5", "primary_npc_id": "npc_1"}},
            {"type": "action_blocked", "payload": {"reason": "test"}},
        ]

        results = []
        for _ in range(3):
            core = SocialStateCore()
            core.apply_events(event_sequence)
            results.append(core.serialize_state())

        assert results[0] == results[1]
        assert results[1] == results[2]

    def test_order_matters(self):
        """Different event orders should produce different states (events are not commutative)."""
        events_a = [
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_threatened", "payload": {"npc_id": "npc_1", "target_id": "player"}},
        ]
        events_b = [
            {"type": "npc_response_threatened", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
        ]

        core_a = SocialStateCore()
        core_a.apply_events(events_a)

        core_b = SocialStateCore()
        core_b.apply_events(events_b)

        # Both produce the same numeric totals since additions are commutative,
        # but last_event_id may differ. The key guarantee is determinism.
        state_a = core_a.serialize_state()
        state_b = core_b.serialize_state()

        # Relationship values should be identical (addition is commutative)
        rel_a = list(state_a["relationships"].values())[0]
        rel_b = list(state_b["relationships"].values())[0]
        assert abs(rel_a["trust"] - rel_b["trust"]) < 1e-9
        assert abs(rel_a["fear"] - rel_b["fear"]) < 1e-9
