"""Unit tests for RPG emotion system."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.emotion import decay_emotions, apply_event_emotion, apply_event_emotion_with_relationships, is_ally


def make_npc(npc_id="npc_1"):
    return type('NPC', (), {
        'id': npc_id,
        'emotional_state': {
            'anger': 0.0,
            'fear': 0.0,
            'loyalty': 0.0,
            'last_update': 0,
            'top_threat': None,
        },
        'relationships': {'allies': ['ally_1']},
    })()


class TestDecayEmotions:
    """Test emotion decay."""

    def test_decay_no_time_passed(self):
        npc = make_npc()
        npc.emotional_state['anger'] = 1.0
        npc.emotional_state['last_update'] = 10
        decay_emotions(npc, 10)
        assert npc.emotional_state['anger'] == 1.0

    def test_decay_reduces_anger(self):
        npc = make_npc()
        npc.emotional_state['anger'] = 1.0
        npc.emotional_state['fear'] = 1.0
        npc.emotional_state['last_update'] = 0
        decay_emotions(npc, 10)
        assert npc.emotional_state['anger'] < 1.0
        assert npc.emotional_state['fear'] < 1.0

    def test_decay_updates_last_update(self):
        npc = make_npc()
        npc.emotional_state['last_update'] = 0
        decay_emotions(npc, 10)
        assert npc.emotional_state['last_update'] == 10

    def test_decay_exponential(self):
        npc = make_npc()
        npc.emotional_state['anger'] = 1.0
        npc.emotional_state['last_update'] = 0
        decay_emotions(npc, 10)
        # 0.9^10 = 0.348...
        expected = 1.0 * (0.9 ** 10)
        assert abs(npc.emotional_state['anger'] - expected) < 0.001


class TestApplyEventEmotion:
    """Test event-based emotion application."""

    def test_damage_to_self(self):
        npc = make_npc()
        event = {"type": "damage", "target": "npc_1", "source": "attacker"}
        apply_event_emotion(npc, event)
        assert npc.emotional_state['anger'] == 2.0
        assert npc.emotional_state['fear'] == 0.5

    def test_damage_with_intensity(self):
        npc = make_npc()
        event = {"type": "damage", "target": "npc_1", "source": "attacker"}
        apply_event_emotion(npc, event, intensity=2.0)
        assert npc.emotional_state['anger'] == 4.0
        assert npc.emotional_state['fear'] == 1.0

    def test_ally_killed(self):
        npc = make_npc()
        event = {"type": "ally_killed", "target": "ally_1"}
        apply_event_emotion(npc, event)
        assert npc.emotional_state['fear'] == 1.5

    def test_damage_to_other_no_effect(self):
        npc = make_npc()
        event = {"type": "damage", "target": "other", "source": "attacker"}
        apply_event_emotion(npc, event)
        assert npc.emotional_state['anger'] == 0.0
        assert npc.emotional_state['fear'] == 0.0


class TestApplyEventEmotionWithRelationships:
    """Test relationship-aware emotion application."""

    def test_ally_attacked_increases_anger(self):
        npc = make_npc()
        event = {"type": "damage", "target": "ally_1", "source": "attacker"}
        apply_event_emotion_with_relationships(npc, event, None)
        assert npc.emotional_state['anger'] > 0

    def test_attacked_by_ally_reduces_loyalty(self):
        npc = make_npc()
        event = {"type": "damage", "target": "npc_1", "source": "ally_1"}
        apply_event_emotion_with_relationships(npc, event, None)
        assert npc.emotional_state['loyalty'] < 0

    def test_damage_to_self(self):
        npc = make_npc()
        event = {"type": "damage", "target": "npc_1", "source": "attacker"}
        apply_event_emotion_with_relationships(npc, event, None)
        assert npc.emotional_state['anger'] == 2.0
        assert npc.emotional_state['fear'] == 0.5


class TestIsAlly:
    """Test ally checking."""

    def test_is_ally(self):
        npc = make_npc()
        assert is_ally(npc, "ally_1", None) is True

    def test_not_ally(self):
        npc = make_npc()
        assert is_ally(npc, "enemy_1", None) is False

    def test_empty_allies(self):
        npc = make_npc()
        npc.relationships['allies'] = []
        assert is_ally(npc, "anyone", None) is False