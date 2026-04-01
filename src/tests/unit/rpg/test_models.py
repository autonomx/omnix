"""Unit tests for RPG core models."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.models import SceneOutput
# GameSession, World, Player, NPC are in rpg.models module file, not the models package
import importlib.util
_spec = importlib.util.spec_from_file_location("rpg_models_module", os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app', 'rpg', 'models.py'))
_models_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_models_module)
GameSession = _models_module.GameSession
World = _models_module.World
Player = _models_module.Player
NPC = _models_module.NPC


class TestSceneOutput:
    """Test SceneOutput model."""

    def test_create_scene_output(self):
        output = SceneOutput(
            location="Town Square",
            scene_type="combat",
            tone="tense",
            tension=0.7,
            narration="A fight breaks out",
            characters=[{"name": "Guard", "dialogue": "Halt!", "emotion": "angry"}],
            choices=["Fight", "Flee", "Talk"],
            event={"type": "damage"}
        )
        assert output.location == "Town Square"
        assert output.scene_type == "combat"
        assert output.tone == "tense"
        assert output.tension == 0.7
        assert len(output.characters) == 1
        assert len(output.choices) == 3

    def test_to_dict(self):
        output = SceneOutput(
            location="Forest",
            scene_type="exploration",
            tone="calm",
            tension=0.2,
            narration="You walk through the forest",
            characters=[],
            choices=["Continue", "Return"]
        )
        d = output.to_dict()
        assert d["location"] == "Forest"
        assert d["scene_type"] == "exploration"
        assert d["characters"] == []
        assert d["choices"] == ["Continue", "Return"]

    def test_event_optional(self):
        output = SceneOutput(
            location="Cave",
            scene_type="discovery",
            tone="mysterious",
            tension=0.5,
            narration="You find a hidden passage",
            characters=[],
            choices=[]
        )
        assert output.event is None


class TestWorld:
    """Test World model."""

    def test_default_world(self):
        world = World()
        assert world.entities == {}
        assert world.locations == {}
        assert world.time == 0
        assert world.size == (20, 20)

    def test_custom_size(self):
        world = World(size=(50, 50))
        assert world.size == (50, 50)


class TestPlayer:
    """Test Player model."""

    def test_default_player(self):
        player = Player()
        assert player.id == "player"
        assert player.hp == 100
        assert player.profile == {}


class TestNPC:
    """Test NPC model."""

    def test_create_npc(self):
        npc = NPC("npc_1", "Guard")
        assert npc.id == "npc_1"
        assert npc.name == "Guard"
        assert npc.hp == 100
        assert npc.is_active is True
        assert npc.goal is None
        assert npc.plan == []
        assert npc.memory == []
        assert npc.relationships == {}
        assert npc.position == (0, 0)
        assert npc.session is None
        assert npc.perception_radius == 5

    def test_emotional_state_defaults(self):
        npc = NPC("npc_1", "Guard")
        assert npc.emotional_state["anger"] == 0.0
        assert npc.emotional_state["fear"] == 0.0
        assert npc.emotional_state["loyalty"] == 0.0
        assert npc.emotional_state["last_update"] == 0
        assert npc.emotional_state["top_threat"] is None


class TestGameSession:
    """Test GameSession model."""

    def test_create_session(self):
        session = GameSession()
        assert session.event_log == []
        assert isinstance(session.world, World)
        assert isinstance(session.player, Player)
        assert session.npcs == []
        assert session.story_arcs == []
        assert session.recent_events == []
        assert session.narrative_state["tension"] == 0.3
        assert session.narrative_state["last_mode"] == "exploration"
        assert session.narrative_state["focus_npc"] is None
        assert session.narrative_state["phase"] == "setup"

    def test_add_npc(self):
        session = GameSession()
        npc = NPC("npc_1", "Guard")
        session.add_npc(npc)
        assert npc in session.npcs
        assert npc.session is session

    def test_config_tone(self):
        session = GameSession()
        assert session.config.tone == "neutral"