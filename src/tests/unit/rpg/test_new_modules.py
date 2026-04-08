"""Tests for new TIER 1-3 modules: ActionRegistry, MemorySummarizer, WorldState, Narrator."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.memory.summarizer import MemorySummarizer
from rpg.narration.narrator import NarratorAgent
from rpg.tools.action_registry import (
    ActionRegistry,
    ActionRegistryError,
    action_attack,
    action_heal,
    action_move,
    action_speak,
    register_default_actions,
)
from rpg.world.world_state import WorldState

# =========================================================
# ActionRegistry Tests
# =========================================================

class TestActionRegistry:
    """Tests for the ActionRegistry tool system."""

    def test_register_and_execute(self):
        """Test registering and executing a custom action."""
        registry = ActionRegistry(world=None)

        def my_action(world, param1, param2=10):
            return {"events": [{"type": "custom", "p1": param1, "p2": param2}]}

        registry.register("custom", my_action, "A custom action",
                          {"param1": "First param", "param2": "Second param"})

        assert registry.has("custom")
        assert "custom" in registry.list_actions()

        result = registry.execute("custom", param1="test", param2=20)
        assert result["events"][0]["type"] == "custom"
        assert result["events"][0]["p1"] == "test"

    def test_execute_missing_action(self):
        """Test executing a non-existent action raises error."""
        registry = ActionRegistry()
        with pytest.raises(ActionRegistryError, match="not found"):
            registry.execute("nonexistent")

    def test_execute_action_dict(self):
        """Test executing an action from dict representation."""
        registry = ActionRegistry()
        registry.register("test", lambda w, x: {"events": [{"type": "test", "x": x}]})

        action_dict = {"action": "test", "parameters": {"x": 42}}
        result = registry.execute_action_dict(action_dict)
        assert result["events"][0]["x"] == 42

    def test_execute_action_dict_missing_key(self):
        """Test execute_action_dict with missing 'action' key."""
        registry = ActionRegistry()
        with pytest.raises(ActionRegistryError, match="missing 'action'"):
            registry.execute_action_dict({"parameters": {}})

    def test_unregister(self):
        """Test unregistering an action."""
        registry = ActionRegistry()
        registry.register("temp", lambda w: {"events": []})
        registry.unregister("temp")
        assert not registry.has("temp")

    def test_unregister_missing(self):
        """Test unregistering a non-existent action."""
        registry = ActionRegistry()
        with pytest.raises(ActionRegistryError, match="not found"):
            registry.unregister("missing")

    def test_action_attack_with_entity(self):
        """Test attack action with mock world entity."""
        world = MagicMock()
        target_entity = MagicMock()
        target_entity.hp = 50
        target_entity.is_active = True
        world.get_entity.return_value = target_entity

        result = action_attack(world, source="player", target="goblin", damage=10)
        assert len(result["events"]) == 1
        assert result["events"][0]["type"] == "damage"
        assert result["events"][0]["amount"] == 10
        assert target_entity.hp == 40

    def test_action_attack_causes_death(self):
        """Test attack action causes death event when HP reaches 0."""
        world = MagicMock()
        target_entity = MagicMock()
        target_entity.hp = 5
        target_entity.is_active = True
        world.get_entity.return_value = target_entity

        result = action_attack(world, source="player", target="goblin", damage=10)
        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "damage"
        assert result["events"][1]["type"] == "death"
        assert target_entity.is_active is False

    def test_action_heal(self):
        """Test heal action restores HP."""
        world = MagicMock()
        target_entity = MagicMock()
        target_entity.hp = 50
        target_entity.max_hp = 100
        world.get_entity.return_value = target_entity

        result = action_heal(world, source="healer", target="wounded", amount=20)
        assert target_entity.hp == 70
        assert result["events"][0]["type"] == "heal"

    def test_register_default_actions(self):
        """Test registering default actions."""
        registry = ActionRegistry()
        register_default_actions(registry)

        expected = ["attack", "move", "speak", "heal", "spawn", "update_relationship", "flee"]
        for name in expected:
            assert registry.has(name)

    def test_action_speak(self):
        """Test speak action generates speak event."""
        result = action_speak(None, speaker="npc1", target="npc2", message="Hello!")
        assert result["events"][0]["type"] == "speak"
        assert result["events"][0]["message"] == "Hello!"

    def test_get_prompt_text(self):
        """Test getting formatted action descriptions."""
        registry = ActionRegistry()
        register_default_actions(registry)
        text = registry.get_prompt_text()
        assert "Available Actions:" in text
        assert "attack(" in text

    def test_reset(self):
        """Test resetting the registry."""
        registry = ActionRegistry()
        register_default_actions(registry)
        registry.reset()
        assert len(registry.list_actions()) == 0


# =========================================================
# MemorySummarizer Tests
# =========================================================

class TestMemorySummarizer:
    """Tests for the MemorySummarizer."""

    def test_summarize_empty(self):
        """Test summarizing empty episode list."""
        summarizer = MemorySummarizer()
        assert summarizer.summarize([]) == ""

    def test_summarize_single_event_dict(self):
        """Test summarizing a single event dict."""
        summarizer = MemorySummarizer()
        event = {"type": "damage", "source": "player", "target": "goblin", "amount": 10}
        result = summarizer.summarize([event])
        assert "player" in result
        assert "goblin" in result

    def test_summarize_death_event(self):
        """Test summarizing death event."""
        summarizer = MemorySummarizer()
        event = {"type": "death", "source": "player", "target": "boss"}
        result = summarizer.summarize([event])
        assert "killed" in result.lower() or "died" in result.lower()

    def test_summarize_heal_event(self):
        """Test summarizing heal event."""
        summarizer = MemorySummarizer()
        event = {"type": "heal", "source": "cleric", "target": "warrior", "amount": 30}
        result = summarizer.summarize([event])
        assert "heal" in result.lower()

    def test_summarize_episode_object(self):
        """Test summarizing an Episode-like object."""
        summarizer = MemorySummarizer()
        episode = MagicMock()
        episode.summary = "The player fought the dragon"
        episode.tags = ["combat", "boss"]
        episode.entities = {"player", "dragon"}

        result = summarizer.summarize([episode])
        assert "dragon" in result

    def test_heuristic_summary_multiple_events(self):
        """Test heuristic summarization of multiple events."""
        summarizer = MemorySummarizer()
        events = [
            {"type": "damage", "source": "A", "target": "B"},
            {"type": "damage", "source": "A", "target": "C"},
            {"type": "heal", "source": "D", "target": "B"},
        ]
        result = summarizer.summarize(events)
        assert len(result) > 0

    def test_compress_memory_with_mock_manager(self):
        """Test compress_memory with a mock MemoryManager."""
        summarizer = MemorySummarizer(max_total_tokens=50)
        mock_manager = MagicMock()

        ep1 = MagicMock()
        ep1.summary = "Short summary"
        ep1.tags = ["combat"]

        ep2 = MagicMock()
        ep2.summary = "Another summary"
        ep2.tags = ["dialogue"]

        mock_manager.retrieve.return_value = [(0.9, ep1), (0.7, ep2)]

        result = summarizer.compress_memory(mock_manager, max_tokens=30)
        assert len(result) > 0

    def test_summarize_item_belief(self):
        """Test summarizing a belief dict."""
        summarizer = MemorySummarizer()
        belief = {
            "type": "relationship",
            "entity": "Alice",
            "target_entity": "Bob",
            "value": -0.5,
            "reason": "Alice hates Bob",
        }
        result = summarizer._summarize_item(belief)
        assert "negative" in result or "hates" in result


# =========================================================
# WorldState Tests
# =========================================================

class TestWorldState:
    """Tests for the WorldState layer."""

    def test_add_and_get_entity(self):
        """Test adding and retrieving entities."""
        ws = WorldState()
        ws.add_entity("player", {"hp": 100, "position": (0, 0)})
        assert ws.has_entity("player")
        entity = ws.get_entity("player")
        assert entity["hp"] == 100

    def test_remove_entity(self):
        """Test removing an entity."""
        ws = WorldState()
        ws.add_entity("temp", {"hp": 50})
        result = ws.remove_entity("temp")
        assert result is not None
        assert not ws.has_entity("temp")

    def test_update_entity(self):
        """Test updating entity properties."""
        ws = WorldState()
        ws.add_entity("player", {"hp": 100})
        ws.update_entity("player", {"hp": 80, "status": "wounded"})
        entity = ws.get_entity("player")
        assert entity["hp"] == 80
        assert entity["status"] == "wounded"

    def test_apply_damage(self):
        """Test applying damage event."""
        ws = WorldState()
        ws.add_entity("goblin", {"hp": 30, "is_active": True})

        event = {"type": "damage", "target": "goblin", "amount": 10}
        ws.apply_event(event)

        assert ws.get_entity("goblin")["hp"] == 20

    def test_apply_death(self):
        """Test applying death event."""
        ws = WorldState()
        ws.add_entity("goblin", {"hp": 10, "is_active": True})

        event = {"type": "death", "target": "goblin", "source": "player"}
        ws.apply_event(event)

        assert ws.get_entity("goblin")["hp"] == 0
        assert ws.get_entity("goblin")["is_active"] is False
        assert not ws.has_entity("goblin") if "goblin" in ws.get_active_entities() else True

    def test_apply_heal(self):
        """Test applying heal event."""
        ws = WorldState()
        ws.add_entity("player", {"hp": 50, "max_hp": 100})

        event = {"type": "heal", "target": "player", "amount": 30}
        ws.apply_event(event)

        assert ws.get_entity("player")["hp"] == 80

    def test_relationship(self):
        """Test relationship management."""
        ws = WorldState()
        ws.update_relationship("player", "goblin", -0.5)
        assert ws.has_hostile_relationship("player", "goblin")
        assert not ws.has_friendly_relationship("player", "goblin")

    def test_relationship_symmetric(self):
        """Test relationships are symmetric."""
        ws = WorldState()
        ws.update_relationship("A", "B", -0.5)
        assert ws.get_relationship("A", "B") == ws.get_relationship("B", "A")

    def test_relationship_clamped(self):
        """Test relationship values are clamped to [-1, 1]."""
        ws = WorldState()
        ws.update_relationship("A", "B", -10.0)
        assert ws.get_relationship("A", "B") >= -1.0
        ws.update_relationship("A", "B", 10.0)
        assert ws.get_relationship("A", "B") <= 1.0

    def test_serialize(self):
        """Test world state serialization."""
        ws = WorldState()
        ws.add_entity("player", {"hp": 100, "position": (0, 0), "is_active": True})
        ws.update_relationship("player", "goblin", -0.3)
        ws.time = 42

        data = ws.serialize()
        assert "entities" in data
        assert "player" in data["entities"]
        assert "relationships" in data
        assert data["time"] == 42

    def test_serialize_for_prompt(self):
        """Test serialization as prompt text."""
        ws = WorldState()
        ws.add_entity("player", {"hp": 100, "position": (0, 0)})
        text = ws.serialize_for_prompt()
        assert "World State" in text
        assert "player" in text

    def test_to_short_summary(self):
        """Test short summary generation."""
        ws = WorldState()
        ws.add_entity("player", {"hp": 100, "is_active": True})
        ws.add_entity("npc1", {"hp": 50, "is_active": True})
        ws.time = 10
        summary = ws.to_short_summary()
        assert "10" in summary
        assert "2" in summary

    def test_get_all_relationships(self):
        """Test getting all relationships for an entity."""
        ws = WorldState()
        ws.update_relationship("A", "B", 0.5)
        ws.update_relationship("A", "C", -0.3)

        rels = ws.get_all_relationships("A")
        assert "B" in rels
        assert "C" in rels

    def test_spawn_entity(self):
        """Test spawn event creates entity."""
        ws = WorldState()
        event = {
            "type": "spawn",
            "entity_id": "new_npc",
            "position": (5, 5),
            "entity_type": "npc",
        }
        ws.apply_event(event)
        assert ws.has_entity("new_npc")

    def test_advance_time(self):
        """Test time advancement."""
        ws = WorldState()
        assert ws.time == 0
        ws.advance_time(5)
        assert ws.time == 5

    def test_reset(self):
        """Test resetting world state."""
        ws = WorldState()
        ws.add_entity("player", {"hp": 100})
        ws.advance_time(10)
        ws.reset()
        assert len(ws.entities) == 0
        assert ws.time == 0


# =========================================================
# NarratorAgent Tests
# =========================================================

class TestNarratorAgent:
    """Tests for the NarratorAgent."""

    def test_generate_empty(self):
        """Test generating narrative from empty events."""
        narrator = NarratorAgent()
        assert narrator.generate([]) == ""

    def test_generate_damage_event(self):
        """Test narrating a damage event."""
        narrator = NarratorAgent(style="minimal")
        events = [{"type": "damage", "source": "player", "target": "goblin", "amount": 10}]
        result = narrator.generate(events)
        assert "player" in result or "damages" in result or "goblin" in result

    def test_generate_death_event(self):
        """Test narrating a death event."""
        narrator = NarratorAgent(style="minimal")
        events = [{"type": "death", "target": "goblin", "source": "player"}]
        result = narrator.generate(events)
        assert "goblin" in result and ("dies" in result or "fallen" in result.lower())

    def test_generate_heal_event(self):
        """Test narrating a heal event."""
        narrator = NarratorAgent(style="minimal")
        events = [{"type": "heal", "source": "cleric", "target": "warrior"}]
        result = narrator.generate(events)
        assert "cleric" in result and "warrior" in result

    def test_generate_speak_event(self):
        """Test narrating a speak event."""
        narrator = NarratorAgent(style="minimal")
        events = [{"type": "speak", "speaker": "npc", "message": "Hello world"}]
        result = narrator.generate(events)
        assert "npc" in result
        assert "Hello world" in result

    def test_filter_non_narratable(self):
        """Test filtering out non-narratable events."""
        narrator = NarratorAgent()
        events = [
            {"type": "damage", "source": "A", "target": "B"},
            {"type": "internal_update"},  # Not narratable
            {"type": "state_change"},  # Not narratable
        ]
        result = narrator._filter_narratable(events)
        assert len(result) == 1
        assert result[0]["type"] == "damage"

    def test_generate_multiple_events_with_transition(self):
        """Test narrating multiple events with transitions."""
        narrator = NarratorAgent(style="dramatic")
        events = [
            {"type": "damage", "source": "A", "target": "B", "amount": 10},
            {"type": "damage", "source": "B", "target": "A", "amount": 5},
        ]
        result = narrator.generate(events)
        assert len(result) > 0

    def test_generate_story_event(self):
        """Test narrating a story event."""
        narrator = NarratorAgent(style="minimal")
        events = [{"type": "story_event", "summary": "A shadow falls over the town"}]
        result = narrator.generate(events)
        assert "shadow" in result.lower()

    def test_event_to_text_damage(self):
        """Test _event_to_text for damage events."""
        narrator = NarratorAgent()
        event = {"type": "damage", "source": "knight", "target": "dragon", "amount": 25}
        text = narrator._event_to_text(event)
        assert "knight" in text
        assert "dragon" in text

    def test_event_to_text_critical_hit(self):
        """Test _event_to_text for critical hit."""
        narrator = NarratorAgent()
        event = {"type": "critical_hit", "source": "archer", "target": "ogre"}
        text = narrator._event_to_text(event)
        assert "devastating" in text.lower() or "archer" in text

    def test_narrate_turn_with_context(self):
        """Test narrate_turn with context string."""
        narrator = NarratorAgent(style="dramatic")  # LLM mode appends context
        events = [{"type": "damage", "source": "A", "target": "B"}]
        result = narrator.narrate_turn(events, context="The battlefield stirs")
        # At minimum, result should contain something from events or context
        assert "A" in result or "battlefield" in result or "damages" in result

    def test_narrate_turn_no_events(self):
        """Test narrate_turn with no events returns context."""
        narrator = NarratorAgent()
        result = narrator.narrate_turn([], context="Silence falls")
        assert result == "Silence falls"

    def test_llm_fallback_on_error(self):
        """Test LLM narration falls back to template on error."""
        def failing_llm(prompt):
            raise RuntimeError("LLM unavailable")

        narrator = NarratorAgent(llm=failing_llm, style="dramatic")
        events = [{"type": "damage", "source": "A", "target": "B", "amount": 10}]
        result = narrator.generate(events)
        assert len(result) > 0  # Should fallback to template

    def test_reset(self):
        """Test narrator reset."""
        narrator = NarratorAgent()
        narrator.reset()  # Should not raise