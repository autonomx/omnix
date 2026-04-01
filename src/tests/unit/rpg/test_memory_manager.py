"""Tests for the 4-layer Memory Manager system."""
import os
import sys
import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app")
)

from rpg.memory.episodic import (
    Episode,
    EpisodeBuilder,
    compute_event_importance,
    compute_episode_importance,
)
from rpg.memory.memory_manager import MemoryManager


class TestEpisode:
    def test_create_episode(self):
        ep = Episode(
            summary="Player attacked guard",
            entities={"player", "guard"},
            importance=0.8,
            tags=["combat"],
            tick_created=10,
        )
        assert ep.id.startswith("ep_")
        assert ep.importance == 0.8
        assert "player" in ep.entities
        assert "combat" in ep.tags

    def test_episode_to_dict_and_from_dict(self):
        original = Episode(
            summary="Test event",
            key_events=[{"type": "damage", "source": "a", "target": "b"}],
            entities={"a", "b"},
            importance=0.5,
            tags=["combat"],
            tick_created=5,
            ttl=100,
        )
        data = original.to_dict()
        restored = Episode.from_dict(data)
        assert restored.summary == original.summary
        assert restored.entities == original.entities
        assert restored.tags == original.tags

    def test_episode_expiry(self):
        permanent = Episode(summary="x", ttl=0, tick_created=0)
        assert not permanent.is_expired(1000)

        temporary = Episode(summary="x", ttl=50, tick_created=0)
        assert not temporary.is_expired(49)
        assert temporary.is_expired(50)

    def test_entity_membership(self):
        ep = Episode(summary="x", entities={"player", "guard"})
        assert ep.has_entity("player")
        assert not ep.has_entity("unknown")
        assert ep.has_any_entity({"player", "foo"})
        assert not ep.has_any_entity({"foo", "bar"})


class TestComputeEventImportance:
    def test_damage_event(self):
        event = {"type": "damage", "source": "a", "target": "b"}
        assert compute_event_importance(event) >= 0.5

    def test_death_event(self):
        event = {"type": "death", "source": "a", "target": "b"}
        assert compute_event_importance(event) >= 0.8

    def test_player_involvement_boost(self):
        regular = compute_event_importance(
            {"type": "damage", "source": "a", "target": "b"}
        )
        player = compute_event_importance(
            {"type": "damage", "source": "player", "target": "b"}
        )
        assert player > regular

    def test_neutral_event(self):
        event = {"type": "move", "source": "a", "target": "b"}
        assert compute_event_importance(event) < 0.3

    def test_unknown_event_type(self):
        event = {"type": "unknown"}
        assert compute_event_importance(event) >= 0.0

    def test_capped_at_1_0(self):
        event = {
            "type": "death",
            "source": "player",
            "target": "b",
            "emotional_intensity": 1.0,
            "memory_type": "narrative_event",
            "summary": "kill death destroy betray",
        }
        assert compute_event_importance(event) <= 1.0


class TestComputeEpisodeImportance:
    def test_empty_events(self):
        assert compute_episode_importance([]) == 0.0

    def test_accumulation_bonus(self):
        events = [
            {"type": "death", "source": "a", "target": "b"},
            {"type": "damage", "source": "a", "target": "b"},
            {"type": "damage", "source": "a", "target": "b"},
        ]
        imp = compute_episode_importance(events)
        single = compute_event_importance(events[0])
        assert imp >= single

    def test_capped_at_1_0(self):
        events = [
            {"type": "death", "source": "player", "target": "b"},
            {"type": "betrayal", "source": "player", "target": "c"},
        ]
        assert compute_episode_importance(events) <= 1.0


class TestEpisodeBuilder:
    def test_build_empty(self):
        ep = EpisodeBuilder().build(current_tick=0)
        assert ep.importance == 0.0

    def test_build_single_event(self):
        events = [{"type": "damage", "source": "guard", "target": "player"}]
        ep = EpisodeBuilder.from_events(events, current_tick=10)
        assert ep.importance > 0
        assert "guard" in ep.entities
        assert "player" in ep.entities

    def test_build_accumulates_tags(self):
        events = [
            {"type": "damage", "source": "a", "target": "b", "tags": ["combat"]},
            {"type": "heal", "source": "a", "target": "c", "tags": ["support"]},
        ]
        ep = EpisodeBuilder.from_events(events, current_tick=0)
        assert "combat" in ep.tags
        assert "heal" in ep.tags

    def test_class_method_from_events(self):
        events = [{"type": "death", "source": "a", "target": "b"}]
        ep = EpisodeBuilder.from_events(events, current_tick=5)
        assert isinstance(ep, Episode)


class TestMemoryManager:
    @pytest.fixture
    def manager(self):
        return MemoryManager(max_raw_events=10, episode_build_threshold=3)

    def test_add_event_layer1(self, manager):
        manager.add_event(
            {"type": "damage", "source": "a", "target": "b"},
            current_tick=1,
        )
        assert len(manager.raw_events) == 1

    def test_add_event_layer2(self, manager):
        manager.add_event(
            {"type": "damage", "source": "a", "target": "b"},
            current_tick=1,
        )
        assert len(manager.narrative_events) == 1

    def test_raw_events_pruned(self):
        mgr = MemoryManager(max_raw_events=3)
        for i in range(10):
            mgr.add_event(
                {"type": "event", "source": f"s{i}", "target": "t"},
                current_tick=i,
            )
        assert len(mgr.raw_events) <= 3

    def test_episode_builds_automatic(self):
        mgr = MemoryManager(episode_build_threshold=3)
        for i in range(3):
            mgr.add_event(
                {"type": "damage", "source": "a", "target": "b"},
                current_tick=i,
            )
        assert len(mgr.episodes) == 1

    def test_belief_from_damage(self, manager):
        manager.add_event(
            {"type": "damage", "source": "guard", "target": "player"},
            current_tick=1,
        )
        # Damage events with importance >= 0.6 (player involved boosts)
        assert len(manager.semantic_beliefs) >= 1
        belief = manager.semantic_beliefs[0]
        assert belief["type"] == "relationship"
        assert belief["value"] < 0

    def test_belief_from_death(self):
        mgr = MemoryManager()
        mgr.add_event(
            {"type": "death", "source": "guard", "target": "player"},
            current_tick=1,
        )
        assert len(mgr.semantic_beliefs) >= 1
        belief = mgr.semantic_beliefs[0]
        assert belief["value"] <= -0.5

    def test_retrieve_by_entity(self, manager):
        ep = Episode(
            summary="Guard fought player",
            entities={"guard", "player"},
            importance=0.7,
            tick_created=1,
        )
        manager.episodes.append(ep)
        results = manager.retrieve(query_entities=["guard"])
        assert len(results) >= 1

    def test_retrieve_returns_top_results(self, manager):
        for i in range(10):
            ep = Episode(
                summary=f"Event {i}",
                entities={"entity"},
                importance=0.1 * (i + 1),
                tick_created=i,
            )
            manager.episodes.append(ep)
        results = manager.retrieve(query_entities=["entity"], limit=3)
        assert len(results) <= 3

    def test_get_context_for_narrative(self, manager):
        ep = Episode(
            summary="Guard attacked player",
            entities={"guard", "player"},
            importance=0.7,
            tick_created=1,
        )
        manager.episodes.append(ep)
        ctx = manager.get_context_for(query_entities=["player"])
        assert "Guard attacked player" in ctx

    def test_get_context_for_structured(self, manager):
        ep = Episode(
            summary="Test",
            entities={"x"},
            importance=0.5,
            tags=["combat"],
            tick_created=0,
        )
        manager.episodes.append(ep)
        ctx = manager.get_context_for(
            query_entities=["x"], format_type="structured"
        )
        assert "## Relevant Memories" in ctx

    def test_consolidate(self, manager):
        for i in range(5):
            manager.add_event(
                {"type": "damage", "source": "a", "target": "b"},
                current_tick=i,
            )
        stats = manager.consolidate(current_tick=10)
        assert "episodes_built" in stats
        assert "episodes_pruned" in stats
        assert "beliefs_updated" in stats

    def test_reset(self, manager):
        manager.add_event(
            {"type": "damage", "source": "a", "target": "b"},
            current_tick=1,
        )
        manager.reset()
        assert len(manager.raw_events) == 0
        assert len(manager.narrative_events) == 0
        assert len(manager.episodes) == 0
        assert len(manager.semantic_beliefs) == 0

    def test_get_stats(self, manager):
        manager.add_event(
            {"type": "damage", "source": "a", "target": "b"},
            current_tick=1,
        )
        stats = manager.get_stats()
        assert stats["raw_events"] == 1
        assert stats["narrative_events"] == 1

    def test_retrieve_for_entity(self, manager):
        ep = Episode(
            summary="Only for player",
            entities={"player"},
            importance=0.5,
            tick_created=0,
        )
        manager.episodes.append(ep)
        results = manager.retrieve_for_entity("player")
        assert len(results) >= 1

    def test_retrieve_for_relationship(self, manager):
        ep = Episode(
            summary="Player and guard conflict",
            entities={"player", "guard"},
            importance=0.6,
            tick_created=0,
        )
        manager.episodes.append(ep)
        results = manager.retrieve_for_relationship("player", "guard")
        assert len(results) >= 1

    def test_entity_index_updated(self, manager):
        ep = Episode(
            summary="test",
            entities={"alice", "bob"},
            importance=0.5,
            tick_created=0,
        )
        manager.episodes.append(ep)
        manager._rebuild_entity_index()
        assert "alice" in manager.entity_index
        assert "bob" in manager.entity_index
        assert ep in manager.entity_index["alice"]

    def test_prune_episodes_by_importance(self):
        mgr = MemoryManager(max_episodes=2)
        for i in range(5):
            ep = Episode(
                summary=f"ep {i}",
                entities={"x"},
                importance=0.1 * (i + 1),
                tick_created=i,
            )
            mgr.episodes.append(ep)
        mgr._prune_episodes()
        assert len(mgr.episodes) <= 2
        assert mgr.episodes[0].importance >= mgr.episodes[-1].importance