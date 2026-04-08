"""Unit tests for RPG scene module."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.scene.grounding import (
    _build_entity_grounding,
    _has_line_of_sight,
    build_grounding_block,
)
from rpg.scene.renderer import render_event_summary, render_scene_deterministic
from rpg.scene.validator import validate_scene


class TestHasLineOfSight:
    """Test line of sight checking."""

    def test_los_close(self):
        assert _has_line_of_sight((0, 0), (5, 0), None) is True

    def test_los_far(self):
        assert _has_line_of_sight((0, 0), (15, 0), None) is False

    def test_los_exact_range(self):
        assert _has_line_of_sight((0, 0), (10, 0), None) is True

    def test_los_diagonal(self):
        # sqrt(6^2 + 8^2) = 10
        assert _has_line_of_sight((0, 0), (6, 8), None) is True


class TestBuildEntityGrounding:
    """Test entity grounding builder."""

    def test_basic_grounding(self):
        entity = type('Entity', (), {
            'position': (5, 5),
            'hp': 80,
        })()
        grounding = _build_entity_grounding("test_entity", entity)
        assert grounding["id"] == "test_entity"
        assert grounding["position"] == (5, 5)
        assert grounding["hp"] == 80
        assert grounding["active"] is True

    def test_dead_entity(self):
        entity = type('Entity', (), {
            'position': (0, 0),
            'hp': 0,
        })()
        grounding = _build_entity_grounding("dead_entity", entity)
        assert grounding["active"] is False

    def test_entity_with_emotional_state(self):
        entity = type('Entity', (), {
            'position': (0, 0),
            'hp': 100,
            'emotional_state': {'anger': 0.5, 'fear': 0.3},
        })()
        grounding = _build_entity_grounding("emotional", entity)
        assert grounding["emotional_state"] == {'anger': 0.5, 'fear': 0.3}

    def test_entity_with_beliefs(self):
        bs = type('BeliefSystem', (), {
            'get': lambda self, key, default=None: {
                'hostile_targets': ['enemy_1'],
                'trusted_allies': ['ally_1'],
                'dangerous_entities': [],
                'world_threat_level': 'low',
                'hostility_intensity': {},
                'trust_intensity': {},
            }.get(key, default),
            'get_summary': lambda self: "Test summary",
        })()
        entity = type('Entity', (), {
            'position': (0, 0),
            'hp': 100,
            'belief_system': bs,
        })()
        grounding = _build_entity_grounding("believer", entity)
        assert grounding["beliefs"]["hostile_targets"] == ['enemy_1']
        assert grounding["beliefs"]["trusted_allies"] == ['ally_1']


class TestBuildGroundingBlock:
    """Test grounding block builder."""

    def _make_session(self):
        npc = type('NPC', (), {
            'id': 'npc_1',
            'position': (0, 0),
            'hp': 100,
            'emotional_state': {},
            'memory': [],
            'relationships': {},
        })()
        world = type('World', (), {'time': 5})()
        return type('Session', (), {
            'npcs': [npc],
            'player': None,
            'world': world,
        })()

    def test_grounding_block_basic(self):
        session = self._make_session()
        grounding = build_grounding_block(session, [], [])
        assert "entities" in grounding
        assert "relationships" in grounding
        assert "distances" in grounding
        assert "visibility" in grounding
        assert "time" in grounding
        assert grounding["time"] == 5

    def test_grounding_block_with_events(self):
        session = self._make_session()
        events = [{"type": "damage", "source": "npc_1", "target": "player"}]
        grounding = build_grounding_block(session, events, [])
        assert grounding["events"] == events

    def test_grounding_block_with_actions(self):
        session = self._make_session()
        actions = [{"npc_id": "npc_1", "action": "attack", "target_id": "player"}]
        grounding = build_grounding_block(session, [], actions)
        assert len(grounding["intentions"]) == 1


class TestRenderSceneDeterministic:
    """Test deterministic scene renderer."""

    def test_empty_grounding(self):
        grounding = {
            "entities": [],
            "events": [],
            "npc_actions": [],
            "time": 0,
        }
        result = render_scene_deterministic(grounding)
        assert "=== TICK 0 ===" in result

    def test_entity_status(self):
        grounding = {
            "entities": [{"id": "npc_1", "hp": 80, "position": (5, 5), "active": True}],
            "events": [],
            "npc_actions": [],
            "time": 1,
        }
        result = render_scene_deterministic(grounding)
        assert "npc_1: HP=80" in result
        assert "(5, 5)" in result

    def test_dead_entity(self):
        grounding = {
            "entities": [{"id": "npc_1", "hp": 0, "position": (0, 0), "active": False}],
            "events": [],
            "npc_actions": [],
            "time": 1,
        }
        result = render_scene_deterministic(grounding)
        assert "npc_1: DEFEATED" in result

    def test_damage_event(self):
        grounding = {
            "entities": [],
            "events": [{"type": "damage", "source": "npc_1", "target": "player", "amount": 10}],
            "npc_actions": [],
            "time": 1,
        }
        result = render_scene_deterministic(grounding)
        assert "npc_1 attacks player for 10 damage" in result

    def test_death_event(self):
        grounding = {
            "entities": [],
            "events": [{"type": "death", "source": "npc_1", "target": "player"}],
            "npc_actions": [],
            "time": 1,
        }
        result = render_scene_deterministic(grounding)
        assert "player has died" in result

    def test_heal_event(self):
        grounding = {
            "entities": [],
            "events": [{"type": "heal", "source": "npc_1", "target": "player", "amount": 20}],
            "npc_actions": [],
            "time": 1,
        }
        result = render_scene_deterministic(grounding)
        assert "npc_1 heals player for 20 HP" in result

    def test_move_event(self):
        grounding = {
            "entities": [],
            "events": [{"type": "move", "source": "npc_1", "destination": (5, 5)}],
            "npc_actions": [],
            "time": 1,
        }
        result = render_scene_deterministic(grounding)
        assert "npc_1 moves to (5, 5)" in result

    def test_intentions(self):
        grounding = {
            "entities": [],
            "events": [],
            "npc_actions": [{"npc_id": "npc_1", "action": "attack", "target": "player"}],
            "time": 1,
        }
        result = render_scene_deterministic(grounding)
        assert "npc_1 intends to attack player" in result


class TestRenderEventSummary:
    """Test event summary renderer."""

    def test_no_events(self):
        assert render_event_summary([]) == "Nothing happened."

    def test_single_damage(self):
        events = [{"type": "damage", "source": "npc_1", "target": "player", "amount": 10}]
        result = render_event_summary(events)
        assert "npc_1 hits player (10 dmg)" in result

    def test_death(self):
        events = [{"type": "death", "source": "npc_1", "target": "player"}]
        result = render_event_summary(events)
        assert "player dies" in result

    def test_heal(self):
        events = [{"type": "heal", "source": "npc_1", "target": "player", "amount": 20}]
        result = render_event_summary(events)
        assert "npc_1 heals player" in result

    def test_multiple_events(self):
        events = [
            {"type": "damage", "source": "npc_1", "target": "player", "amount": 10},
            {"type": "death", "source": "npc_1", "target": "player"},
        ]
        result = render_event_summary(events)
        assert "npc_1 hits player (10 dmg)" in result
        assert "player dies" in result


class TestValidateScene:
    """Test scene validator."""

    def test_valid_scene(self):
        output = "The warrior attacks the orc in the forest."
        grounding = {"entities": [{"id": "warrior"}]}
        assert validate_scene(output, grounding) is True

    def test_hallucination_detection(self):
        output = "A dragon appeared from nowhere."
        grounding = {"entities": []}
        assert validate_scene(output, grounding) is False

    def test_spaceship_hallucination(self):
        output = "A spaceship landed in the village."
        grounding = {"entities": []}
        assert validate_scene(output, grounding) is False

    def test_laser_hallucination(self):
        output = "He fired his laser at the enemy."
        grounding = {"entities": []}
        assert validate_scene(output, grounding) is False