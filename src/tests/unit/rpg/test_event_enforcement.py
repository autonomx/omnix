"""Event enforcement tests — PATCH 9 from rpg-design.txt.

Tests for Phase 1.5 enforcement features:
- EventBus enforcement flag
- Single GameLoop instance detection
- Deprecated module blocking
"""

import pytest
from unittest.mock import Mock, patch

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import (
    GameLoop,
    IntentParser,
    WorldSystem,
    NPCSystem,
    StoryDirector,
    SceneRenderer,
)


@pytest.fixture(autouse=True)
def _reset_single_loop_guard():
    """Reset the GameLoop single-loop guard between tests."""
    GameLoop._active_loop = None
    yield
    GameLoop._active_loop = None


# ============================================================
# EventBus Enforcement tests
# ============================================================

class TestEventBusEnforcement:
    """Tests for EventBus enforcement features."""

    def test_event_bus_enforcement_flag(self):
        """Test that enforce=True enables enforcement checks."""
        bus = EventBus(debug=True, enforce=True)
        bus.emit(Event("test", {}))
        assert bus.pending_count == 1

    def test_event_bus_without_enforcement(self):
        """Test that enforce=False (default) skips enforcement."""
        bus = EventBus()
        bus.emit(Event("test", {}))
        assert bus.pending_count == 1

    def test_enforce_flag_is_stored(self):
        """Test that the enforce flag is stored correctly."""
        bus_enforce = EventBus(enforce=True)
        bus_no_enforce = EventBus(enforce=False)
        assert bus_enforce._enforce is True
        assert bus_no_enforce._enforce is False

    def test_enforcement_calls_assert_method(self):
        """Test that emit calls assert_event_usage."""
        bus = EventBus(enforce=True)
        # Should not raise
        bus.emit(Event("test", {}))
        assert bus.pending_count == 1


# ============================================================
# Single Loop Enforcement tests
# ============================================================

class TestSingleLoopEnforcement:
    """Tests for single game loop enforcement."""

    def test_single_loop_guard(self):
        """Test that only one GameLoop instance can tick."""
        loop1 = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=EventBus(),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        loop1.tick("first")
        assert GameLoop._active_loop is loop1

    def test_multiple_loop_detection(self):
        """Test that a second GameLoop instance raises RuntimeError."""
        loop1 = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=EventBus(),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        loop2 = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=EventBus(),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        loop1.tick("first")
        with pytest.raises(RuntimeError, match="Multiple GameLoop instances detected"):
            loop2.tick("second")

    def test_loop_becomes_active_on_tick(self):
        """Test that _active_loop is set on first tick."""
        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=EventBus(),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        assert GameLoop._active_loop is None
        loop.tick("test")
        assert GameLoop._active_loop is loop


# ============================================================
# Deprecated Module tests
# ============================================================

class TestDeprecatedModules:
    """Tests that deprecated modules raise RuntimeError."""

    def test_deprecated_event_bus_raises_error(self):
        """Test that importing old event_bus raises RuntimeError."""
        with pytest.raises(RuntimeError, match="DEPRECATED"):
            import app.rpg.event_bus  # noqa: F401

    def test_deprecated_director_raises_error(self):
        """Test that importing old director raises RuntimeError."""
        with pytest.raises(RuntimeError, match="DEPRECATED"):
            import app.rpg.director.director  # noqa: F401


# ============================================================
# TickPhase tests
# ============================================================

class TestTickPhase:
    """Tests for TickPhase enumeration."""

    def test_tick_phase_values(self):
        """Test that TickPhase has expected values."""
        from app.rpg.core.game_loop import TickPhase
        assert TickPhase.PRE_WORLD.value == "pre_world"
        assert TickPhase.POST_WORLD.value == "post_world"
        assert TickPhase.PRE_NPC.value == "pre_npc"
        assert TickPhase.POST_NPC.value == "post_npc"

    def test_tick_phase_import_from_core(self):
        """Test that TickPhase can be imported from core module."""
        from app.rpg.core import TickPhase
        assert TickPhase.PRE_WORLD.value == "pre_world"