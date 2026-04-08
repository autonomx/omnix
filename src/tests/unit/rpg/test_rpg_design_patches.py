"""Tests for RPG Design Patches (rpg-design.txt implementation).

Tests for:
- PATCH 1: DirectorAgent (LLM-first multi-step planner)
- PATCH 2: AgentScheduler (Multi-agent orchestration)
- PATCH 3: AutonomousTickManager (Autonomous AI decisions)
- PATCH 4: BehaviorDriver (Memory-driven NPC behavior)
- PATCH 5: SceneManager (Scene/narrative structure)
"""

import unittest
from unittest.mock import MagicMock, patch

from rpg.ai.behavior_driver import BehaviorContext, BehaviorDriver
from rpg.core.agent_scheduler import AgentScheduler, AutonomousTickManager
from rpg.narration.narrator import NarratorAgent
from rpg.scene.scene_manager import Scene, SceneManager
from rpg.story.director_agent import DirectorAgent, DirectorOutput
from rpg.tools.action_registry import ActionRegistry
from rpg.world.world_state import WorldState

# =========================================================
# PATCH 1: DirectorAgent Tests
# =========================================================

class TestDirectorOutput(unittest.TestCase):
    """Test DirectorOutput data class."""

    def test_init_default(self):
        output = DirectorOutput()
        self.assertEqual(output.plan, "")
        self.assertEqual(output.actions, [])
        self.assertEqual(output.reasoning, "")
        self.assertEqual(output.tension_delta, 0.0)

    def test_init_with_values(self):
        output = DirectorOutput(
            plan="Attack the goblins",
            actions=[{"action": "attack", "parameters": {"source": "player"}}],
            reasoning="Goblins are hostile",
            tension_delta=0.3,
        )
        self.assertEqual(output.plan, "Attack the goblins")
        self.assertEqual(len(output.actions), 1)
        self.assertEqual(output.tension_delta, 0.3)

    def test_to_dict(self):
        output = DirectorOutput(plan="Test", actions=[], tension_delta=0.1)
        d = output.to_dict()
        self.assertEqual(d["plan"], "Test")
        self.assertEqual(d["actions"], [])
        self.assertEqual(d["tension_delta"], 0.1)

    def test_from_dict(self):
        d = {
            "plan": "From dict",
            "actions": [{"action": "move"}],
            "reasoning": "Because",
            "tension_delta": -0.2,
        }
        output = DirectorOutput.from_dict(d)
        self.assertEqual(output.plan, "From dict")
        self.assertEqual(len(output.actions), 1)
        self.assertEqual(output.tension_delta, -0.2)

    def test_is_empty(self):
        empty = DirectorOutput()
        self.assertTrue(empty.is_empty())

        non_empty = DirectorOutput(actions=[{"action": "attack"}])
        self.assertFalse(non_empty.is_empty())


class TestDirectorAgent(unittest.TestCase):
    """Test DirectorAgent LLM-first planner."""

    def test_init_default(self):
        agent = DirectorAgent()
        self.assertIsNone(agent.llm)
        self.assertIsInstance(agent.registry, ActionRegistry)
        self.assertEqual(agent.style, "balanced")
        self.assertEqual(agent.max_actions, 5)

    def test_init_with_params(self):
        mock_llm = MagicMock()
        mock_registry = MagicMock()
        agent = DirectorAgent(
            llm=mock_llm,
            registry=mock_registry,
            style="dramatic",
            max_actions=3,
        )
        self.assertEqual(agent.llm, mock_llm)
        self.assertEqual(agent.registry, mock_registry)
        self.assertEqual(agent.style, "dramatic")
        self.assertEqual(agent.max_actions, 3)

    def test_decide_fallback_no_llm(self):
        agent = DirectorAgent()
        output = agent.decide("Hello", world=None)
        self.assertIn("No LLM", output.plan)
        self.assertEqual(output.actions, [])

    def test_decide_with_mock_llm(self):
        mock_llm = MagicMock(return_value='''
{
  "plan": "Escalate tension",
  "reasoning": "Player is aggressive",
  "tension_delta": 0.3,
  "actions": [
    {"action": "attack", "parameters": {"source": "guard", "target": "player", "damage": 5}}
  ]
}
''')
        agent = DirectorAgent(llm=mock_llm)
        output = agent.decide("I attack the guard!")
        self.assertEqual(output.plan, "Escalate tension")
        self.assertEqual(len(output.actions), 1)
        self.assertEqual(output.actions[0]["action"], "attack")
        self.assertEqual(output.tension_delta, 0.3)

    def test_decide_handles_fenced_code_blocks(self):
        mock_llm = MagicMock(return_value='''
```json
{
  "plan": "Test plan",
  "actions": [],
  "reasoning": "Test",
  "tension_delta": 0.0
}
```
''')
        agent = DirectorAgent(llm=mock_llm)
        output = agent.decide("test")
        self.assertEqual(output.plan, "Test plan")

    def test_decide_limits_actions(self):
        mock_llm = MagicMock(return_value='''
{
  "plan": "Many actions",
  "actions": [
    {"action": "a1"}, {"action": "a2"}, {"action": "a3"},
    {"action": "a4"}, {"action": "a5"}, {"action": "a6"},
    {"action": "a7"}
  ],
  "reasoning": "Test",
  "tension_delta": 0.0
}
''')
        agent = DirectorAgent(llm=mock_llm, max_actions=3)
        output = agent.decide("test")
        self.assertLessEqual(len(output.actions), 3)

    def test_quick_decision_aggressive(self):
        agent = DirectorAgent()
        output = agent.quick_decision("I attack the guard!", tension=5.0)
        self.assertTrue(len(output.actions) > 0)
        self.assertEqual(output.actions[0]["action"], "attack")

    def test_quick_decision_diplomatic(self):
        agent = DirectorAgent()
        output = agent.quick_decision("Hello, I come in peace", tension=5.0)
        self.assertEqual(output.tension_delta, -0.1)

    def test_quick_decision_high_tension(self):
        agent = DirectorAgent()
        output = agent.quick_decision("wait", tension=8.0)
        self.assertTrue(len(output.actions) > 0)

    def test_parse_invalid_json(self):
        agent = DirectorAgent()
        output = agent._parse_response("not json at all")
        self.assertIn("Could not parse", output.plan)
        self.assertEqual(output.actions, [])


# =========================================================
# PATCH 2: AgentScheduler Tests
# =========================================================

class TestAgentScheduler(unittest.TestCase):
    """Test AgentScheduler multi-agent orchestration."""

    def setUp(self):
        self.world = WorldState()
        self.world.add_entity("player", {"hp": 100, "is_active": True})
        self.world.add_entity("guard", {"hp": 50, "is_active": True})

        self.registry = ActionRegistry(world=self.world)
        from rpg.tools.action_registry import register_default_actions
        register_default_actions(self.registry)

        self.director = DirectorAgent()
        self.narrator = NarratorAgent(style="minimal")
        self.scheduler = AgentScheduler(
            director=self.director,
            registry=self.registry,
            narrator=self.narrator,
            world=self.world,
        )

    def test_init(self):
        self.assertIsInstance(self.scheduler.director, DirectorAgent)
        self.assertIsInstance(self.scheduler.registry, ActionRegistry)
        self.assertIsInstance(self.scheduler.narrator, NarratorAgent)

    def test_run_turn_no_llm(self):
        # Without LLM, director returns empty plan
        result = self.scheduler.run_turn(
            session=MagicMock(world=self.world),
            player_input="Hello",
        )
        self.assertIn("narration", result)
        self.assertIn("events", result)
        self.assertIn("plan", result)

    def test_run_turn_with_mock_director(self):
        mock_director = MagicMock()
        mock_director.decide.return_value = DirectorOutput(
            plan="Guard attacks",
            actions=[{
                "action": "attack",
                "parameters": {"source": "guard", "target": "player", "damage": 10},
            }],
            reasoning="Guard is hostile",
            tension_delta=0.3,
        )
        scheduler = AgentScheduler(
            director=mock_director,
            registry=self.registry,
            narrator=self.narrator,
            world=self.world,
        )
        result = scheduler.run_turn(
            session=MagicMock(world=self.world),
            player_input="Hello",
        )
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["type"], "damage")
        self.assertIn("narration", result)

    def test_execute_plan(self):
        mock_director = MagicMock()
        plan = DirectorOutput(
            plan="Heal player",
            actions=[{
                "action": "heal",
                "parameters": {"source": "guard", "target": "player", "amount": 20},
            }],
        )
        scheduler = AgentScheduler(
            director=mock_director,
            registry=self.registry,
            world=self.world,
        )
        result = scheduler.execute_plan(plan)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["type"], "heal")

    def test_apply_event_to_world(self):
        event = {"type": "damage", "source": "a", "target": "player", "amount": 5}
        self.scheduler._apply_event_to_world(event)
        player = self.world.get_entity("player")
        self.assertEqual(player["hp"], 95)


# =========================================================
# PATCH 3: AutonomousTickManager Tests
# =========================================================

class TestAutonomousTickManager(unittest.TestCase):
    """Test AutonomousTickManager for AI-driven decisions."""

    def setUp(self):
        self.world = WorldState()
        self.registry = ActionRegistry(world=self.world)
        from rpg.tools.action_registry import register_default_actions
        register_default_actions(self.registry)
        self.scheduler = AgentScheduler(
            registry=self.registry,
            world=self.world,
        )
        self.tick_mgr = AutonomousTickManager(
            scheduler=self.scheduler,
            default_interval=3,
        )

    def test_should_tick_turn_based(self):
        # Should tick every 3 turns
        self.assertFalse(self.tick_mgr.should_tick())  # 1
        self.assertFalse(self.tick_mgr.should_tick())  # 2
        self.assertTrue(self.tick_mgr.should_tick())   # 3

    def test_should_tick_time_based(self):
        self.assertTrue(
            self.tick_mgr.should_tick(
                player_last_active=100.0,
                current_time=135.0,
                idle_threshold=30.0,
            )
        )

    def test_should_tick_not_idle(self):
        self.assertFalse(
            self.tick_mgr.should_tick(
                player_last_active=100.0,
                current_time=110.0,
                idle_threshold=30.0,
            )
        )

    def test_autonomous_tick(self):
        result = self.tick_mgr.autonomous_tick()
        self.assertIn("events", result)
        self.assertIn("narration", result)

    def test_tick_alias(self):
        result = self.tick_mgr.tick()
        self.assertIn("events", result)


# =========================================================
# PATCH 4: BehaviorDriver Tests
# =========================================================

class TestBehaviorContext(unittest.TestCase):
    """Test BehaviorContext data class."""

    def test_init_default(self):
        ctx = BehaviorContext(npc_id="guard")
        self.assertEqual(ctx.npc_id, "guard")
        self.assertEqual(ctx.beliefs, {})
        self.assertEqual(ctx.relationships, {})

    def test_to_prompt(self):
        ctx = BehaviorContext(
            npc_id="guard",
            beliefs={"hostile": {"reason": "Player attacked me", "value": -0.5}},
            relationships={"player": -0.5},
            recent_memories=[{"type": "damage", "summary": "Player hit me"}],
        )
        prompt = ctx.to_prompt()
        self.assertIn("guard", prompt)
        self.assertIn("BELIEFS", prompt)
        self.assertIn("RELATIONSHIPS", prompt)
        self.assertIn("RECENT MEMORIES", prompt)

    def test_to_dict(self):
        ctx = BehaviorContext(
            npc_id="guard",
            beliefs={"key": "value"},
            relationships={"player": 0.5},
        )
        d = ctx.to_dict()
        self.assertEqual(d["npc_id"], "guard")
        self.assertEqual(d["beliefs"], {"key": "value"})


class TestBehaviorDriver(unittest.TestCase):
    """Test BehaviorDriver for memory-driven NPC behavior."""

    def setUp(self):
        self.driver = BehaviorDriver()

    def test_init(self):
        self.assertIsNone(self.driver.memory_manager)
        self.assertIsInstance(self.driver.belief_system, type(self.driver.belief_system))

    def test_build_decision_context(self):
        ctx = self.driver.build_decision_context("guard", entities=["player"])
        self.assertIsInstance(ctx, BehaviorContext)
        self.assertEqual(ctx.npc_id, "guard")

    def test_generate_reasoning(self):
        ctx = BehaviorContext(
            npc_id="guard",
            beliefs={"hostile": {"reason": "Player attacked", "value": -0.5}},
            relationships={"player": -0.5},
            recent_memories=[{"type": "damage"}],
        )
        reasoning = self.driver.generate_reasoning(ctx, "attack")
        self.assertIn("reasoning", reasoning)
        self.assertIn("motivation", reasoning)
        self.assertIn("action", reasoning)

    def test_build_decision_prompt(self):
        ctx = BehaviorContext(npc_id="guard")
        prompt = self.driver.build_decision_prompt(ctx)
        self.assertIn("guard", prompt)
        self.assertIn("Return JSON", prompt)


# =========================================================
# PATCH 5: SceneManager Tests
# =========================================================

class TestScene(unittest.TestCase):
    """Test Scene class."""

    def test_init(self):
        scene = Scene(goal="Escape the dungeon", participants={"player"})
        self.assertEqual(scene.goal, "Escape the dungeon")
        self.assertIn("player", scene.participants)
        self.assertEqual(scene.progress, 0.0)
        self.assertFalse(scene.completed)

    def test_add_event_progress(self):
        scene = Scene(goal="Fight", max_progress=1.0)
        scene.add_event({"type": "damage", "source": "a", "target": "b"})
        self.assertGreater(scene.progress, 0)

    def test_is_complete(self):
        scene = Scene(goal="Test", max_progress=0.5)
        scene.progress = 0.6
        self.assertTrue(scene.is_complete())

    def test_is_not_complete(self):
        scene = Scene(goal="Test", max_progress=1.0)
        scene.progress = 0.3
        self.assertFalse(scene.is_complete())

    def test_add_remove_participant(self):
        scene = Scene(goal="Test")
        scene.add_participant("player")
        self.assertIn("player", scene.participants)
        scene.remove_participant("player")
        self.assertNotIn("player", scene.participants)

    def test_to_dict(self):
        scene = Scene(goal="Test", participants={"player", "guard"})
        d = scene.to_dict()
        self.assertEqual(d["goal"], "Test")
        self.assertIn("player", d["participants"])

    def test_summary(self):
        scene = Scene(goal="Fight the dragon", max_progress=1.0)
        scene.progress = 0.5
        summary = scene.summary()
        self.assertIn("IN PROGRESS", summary)
        self.assertIn("Fight the dragon", summary)


class TestSceneManager(unittest.TestCase):
    """Test SceneManager class."""

    def setUp(self):
        self.manager = SceneManager()

    def test_init(self):
        self.assertIsNone(self.manager.current_scene)
        self.assertEqual(len(self.manager.scene_history), 0)

    def test_new_scene(self):
        scene = self.manager.new_scene("Fight", {"player", "guard"})
        self.assertEqual(scene.goal, "Fight")
        self.assertEqual(self.manager.current_scene, scene)

    def test_new_scene_archives_old(self):
        self.manager.new_scene("Scene 1")
        self.manager.new_scene("Scene 2")
        self.assertEqual(len(self.manager.scene_history), 1)
        self.assertEqual(self.manager.scene_history[0].goal, "Scene 1")

    def test_update_scene(self):
        self.manager.new_scene("Fight", {"player"})
        self.manager.update_scene([
            {"type": "damage", "source": "player", "target": "guard"},
            {"type": "speak", "speaker": "player", "target": "guard", "message": "Hi"},
        ])
        self.assertGreater(self.manager.current_scene.progress, 0)
        self.assertIn("guard", self.manager.current_scene.participants)

    def test_is_scene_complete(self):
        self.manager.new_scene("Quick fight", max_progress=0.1)
        self.manager.update_scene([
            {"type": "damage", "source": "a", "target": "b"},
        ])
        # May or may not be complete depending on progress
        self.assertIsInstance(self.manager.is_scene_complete(), bool)

    def test_advance_scene(self):
        self.manager.new_scene("Scene 1")
        new_scene = self.manager.advance_scene("Scene 2")
        self.assertEqual(new_scene.goal, "Scene 2")
        self.assertEqual(len(self.manager.scene_history), 1)

    def test_get_scene_context(self):
        self.manager.new_scene("Fight", {"player"})
        ctx = self.manager.get_scene_context()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["current_scene"], "Fight")

    def test_get_scene_context_no_scene(self):
        ctx = self.manager.get_scene_context()
        self.assertIsNone(ctx)

    def test_register_and_create_template(self):
        self.manager.register_template("combat", "Fight to the death", tags=["combat"])
        scene = self.manager.create_from_template("combat", {"player"})
        self.assertIsNotNone(scene)
        self.assertEqual(scene.goal, "Fight to the death")
        self.assertIn("combat", scene.tags)

    def test_create_from_template_missing(self):
        scene = self.manager.create_from_template("nonexistent")
        self.assertIsNone(scene)

    def test_new_scene_from_events(self):
        events = [
            {"type": "damage", "source": "player", "target": "guard"},
            {"type": "damage", "source": "guard", "target": "player"},
        ]
        scene = self.manager.new_scene_from_events(events)
        self.assertIsNotNone(scene)
        self.assertIn("player", scene.participants)
        self.assertIn("guard", scene.participants)

    def test_new_scene_from_empty_events(self):
        scene = self.manager.new_scene_from_events([])
        self.assertIsNone(scene)

    def test_get_scene_summary(self):
        self.manager.new_scene("Test")
        summary = self.manager.get_scene_summary()
        self.assertIn("Scene Status", summary)

    def test_reset(self):
        self.manager.new_scene("Test")
        self.manager.reset()
        self.assertIsNone(self.manager.current_scene)
        self.assertEqual(len(self.manager.scene_history), 0)


if __name__ == "__main__":
    unittest.main()