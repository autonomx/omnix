"""Phase 7.6 — Functional Tests for Persistent Social State.

Covers:
- Social interaction updates persistent relationship state
- Rumor seeded event creates active rumor record
- Threatening response increases fear and hostility
- Dashboard methods return UI-safe payloads
"""

from __future__ import annotations

from app.rpg.social_state.core import SocialStateCore
from app.rpg.social_state.query import SocialStateQuery
from app.rpg.creator.presenters import CreatorStatePresenter


class TestSocialInteractionUpdatesPersistentRelationshipState:
    def test_social_interaction_updates_persistent_relationship_state(self):
        """Resolving social interactions updates persistent social state."""
        core = SocialStateCore()

        # Simulate a sequence of social interactions
        events = [
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
            {"type": "npc_response_refused", "payload": {"npc_id": "npc_2", "target_id": "player"}},
        ]
        core.apply_events(events)

        state = core.get_state()
        query = core.get_query()

        # npc_1 should have positive relationship with player
        rel_npc1 = query.get_relationship(state, "npc_1", "player")
        assert rel_npc1 is not None
        assert rel_npc1["trust"] > 0.0
        assert rel_npc1["respect"] > 0.0

        # npc_2 should have negative trust with player
        rel_npc2 = query.get_relationship(state, "npc_2", "player")
        assert rel_npc2 is not None
        assert rel_npc2["trust"] < 0.0
        assert rel_npc2["hostility"] > 0.0


class TestRumorSeedEventCreatesRumorRecord:
    def test_rumor_seed_event_creates_rumor_record(self):
        """rumor_seeded events should create active rumor records."""
        core = SocialStateCore()

        event = {
            "type": "rumor_seeded",
            "payload": {
                "rumor_id": "rumor_vault",
                "source_npc_id": "npc_thief",
                "subject_id": "player",
                "rumor_type": "suspicion",
                "summary": "Player was seen near the vault at night",
                "location": "bank_district",
            },
        }
        core.apply_event(event)

        state = core.get_state()
        assert "rumor_vault" in state.rumors
        rumor = state.rumors["rumor_vault"]
        assert rumor.active is True
        assert rumor.rumor_type == "suspicion"
        assert rumor.spread_level == 0
        assert rumor.source_npc_id == "npc_thief"

    def test_multiple_rumors_coexist(self):
        core = SocialStateCore()
        core.apply_events([
            {
                "type": "rumor_seeded",
                "payload": {
                    "rumor_id": "r1",
                    "source_npc_id": "npc_1",
                    "subject_id": "player",
                    "rumor_type": "gossip",
                    "summary": "Gossip 1",
                    "location": "tavern",
                },
            },
            {
                "type": "rumor_seeded",
                "payload": {
                    "rumor_id": "r2",
                    "source_npc_id": "npc_2",
                    "subject_id": "player",
                    "rumor_type": "warning",
                    "summary": "Warning 2",
                    "location": "market",
                },
            },
        ])
        state = core.get_state()
        assert len(state.rumors) == 2


class TestThreateningResponseIncreasesFearAndHostility:
    def test_threatening_response_increases_fear_and_hostility(self):
        """npc_response_threatened should increase fear and hostility."""
        core = SocialStateCore()

        event = {
            "type": "npc_response_threatened",
            "payload": {"npc_id": "npc_guard", "target_id": "player"},
        }
        core.apply_event(event)

        state = core.get_state()
        rel = list(state.relationships.values())[0]
        assert rel.fear == 0.15
        assert rel.hostility == 0.15

        # Reputation should also worsen
        rep = list(state.reputation_edges.values())[0]
        assert rep.score < 0.0

    def test_repeated_threats_accumulate(self):
        core = SocialStateCore()
        for _ in range(3):
            core.apply_event({
                "type": "npc_response_threatened",
                "payload": {"npc_id": "npc_guard", "target_id": "player"},
            })
        state = core.get_state()
        rel = list(state.relationships.values())[0]
        assert abs(rel.fear - 0.45) < 1e-9
        assert abs(rel.hostility - 0.45) < 1e-9


class TestSocialDashboardReturnsUISafeShape:
    def test_social_dashboard_returns_ui_safe_shape(self):
        """Dashboard methods should return UI-safe payloads."""
        core = SocialStateCore()
        core.apply_events([
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
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
            {"type": "npc_secondary_supported", "payload": {"npc_id": "npc_2", "primary_npc_id": "npc_1"}},
        ])

        # Test query-based dashboard
        query = core.get_query()
        state = core.get_state()
        view = query.build_npc_social_view(state, "npc_1", "player")
        assert "npc_id" in view
        assert "relationship" in view
        assert "reputation" in view
        assert "active_rumors" in view

    def test_presenter_social_dashboard_shape(self):
        core = SocialStateCore()
        core.apply_events([
            {"type": "npc_response_agreed", "payload": {"npc_id": "npc_1", "target_id": "player"}},
        ])
        presenter = CreatorStatePresenter()
        dashboard = presenter.present_social_dashboard(core)
        assert dashboard["title"] == "Social State"
        assert "relationships" in dashboard
        assert "rumors" in dashboard
        assert "alliances" in dashboard

    def test_presenter_social_dashboard_none_core(self):
        presenter = CreatorStatePresenter()
        dashboard = presenter.present_social_dashboard(None)
        assert dashboard["title"] == "Social State"
        assert dashboard["relationships"] == []

    def test_presenter_npc_social_view_shape(self):
        core = SocialStateCore()
        core.apply_event({
            "type": "npc_response_agreed",
            "payload": {"npc_id": "npc_1", "target_id": "player"},
        })
        query = core.get_query()
        state = core.get_state()
        view = query.build_npc_social_view(state, "npc_1", "player")

        presenter = CreatorStatePresenter()
        presented = presenter.present_npc_social_view(view)
        assert "npc_id" in presented
        assert "relationship" in presented
        assert "active_rumors" in presented

    def test_presenter_present_rumor(self):
        presenter = CreatorStatePresenter()
        rumor = presenter.present_rumor({
            "rumor_id": "r1",
            "rumor_type": "gossip",
            "summary": "test",
            "spread_level": 2,
            "active": True,
        })
        assert rumor["rumor_id"] == "r1"
        assert rumor["spread_level"] == 2
        assert rumor["active"] is True
