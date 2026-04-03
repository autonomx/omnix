"""Story Director — Unified narrative processing.

PHASE 1 — STABILIZE Step 4:
This is the SINGLE authority for narrative processing as specified in rpg-design.txt.

PHASE 1.5 — ENFORCEMENT PATCH:
- Added structured event types (narrative_beat_selected + scene_generated)
- Added source field to events for system identity tracking
- Enhanced event payloads with more debug info

All other narrative directors (narrative_director.py, narrative_director_t18.py,
director/director.py) are DEPRECATED and should route through this class.

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.
"""

from typing import Any, Dict, List, Optional

from ..core.event_bus import Event, EventBus


class StoryDirector:
    """Unified story director for narrative processing.

    This class replaces all duplicated narrative directors with a single
    authority. It processes events and player intents to produce narrative
    output for scene rendering.

    The Director Loop:
        1. Analyze world state from events
        2. Update story arcs
        3. Select next narrative beat
        4. Generate scene

    Attributes:
        arc_manager: Manages active story arcs.
        plot_engine: Selects narrative beats.
        scene_engine: Generates scenes from beats.
    """

    def __init__(
        self,
        arc_manager: Optional[Any] = None,
        plot_engine: Optional[Any] = None,
        scene_engine: Optional[Any] = None,
    ):
        """Initialize the StoryDirector.

        Args:
            arc_manager: Story arc manager. If None, uses DefaultArcManager.
            plot_engine: Plot engine for beat selection. If None, uses DefaultPlotEngine.
            scene_engine: Scene engine for scene generation. If None, uses DefaultSceneEngine.
        """
        self.arc_manager = arc_manager or DefaultArcManager()
        self.plot_engine = plot_engine or DefaultPlotEngine()
        self.scene_engine = scene_engine or DefaultSceneEngine()

        self._event_log: List[Dict[str, Any]] = []
        self._tick_count = 0

    def process(
        self,
        events: List[Event],
        player_intent: Dict[str, Any],
        event_bus: Any,
    ) -> Dict[str, Any]:
        """Process events and player intent into narrative output.

        This implements the unified Director pipeline:
            1. Analyze world state from events
            2. Update story arcs
            3. Select next narrative beat
            4. Generate scene

        Args:
            events: Events collected from the EventBus.
            player_intent: The parsed player intent dictionary.
            event_bus: The shared EventBus for emitting narrative events.

        Returns:
            Narrative data dictionary suitable for scene rendering.
        """
        self._tick_count += 1

        # 1. Analyze world state from events
        world_state = self._analyze(events)

        # 2. Update story arcs
        active_arcs = self.arc_manager.update(world_state)

        # 3. Select next narrative beat
        next_beat = self.plot_engine.select(active_arcs, player_intent)

        # Emit narrative beat selected event (structured event type)
        event_bus.emit(Event(
            "narrative_beat_selected",
            {
                "beat": next_beat,
                "tick": self._tick_count,
            },
            source="story_director"
        ))

        # 4. Generate scene
        scene = self.scene_engine.generate(next_beat)

        # Emit scene_generated event with enhanced payload
        event_bus.emit(Event(
            "scene_generated",
            {
                "tick": self._tick_count,
                "beat": next_beat,
                "scene": scene,
            },
            source="story_director"
        ))

        return scene

    def _analyze(self, events: List[Event]) -> Dict[str, Any]:
        """Analyze events to produce a world state summary.

        Args:
            events: List of events from the EventBus.

        Returns:
            World state dictionary summarizing current conditions.
        """
        # Record events for history
        for event in events:
            self._event_log.append({
                "type": event.type,
                "payload": event.payload,
                "tick": self._tick_count,
            })

        return {
            "events": [
                {"type": e.type, "payload": e.payload}
                for e in events
            ],
            "event_count": len(events),
            "tick": self._tick_count,
        }

    @property
    def tick_count(self) -> int:
        """Number of ticks processed."""
        return self._tick_count

    @property
    def event_log(self) -> List[Dict[str, Any]]:
        """Access the event log for debugging."""
        return self._event_log[:]

    def reset(self) -> None:
        """Reset the director state."""
        self._event_log.clear()
        self._tick_count = 0
        self.arc_manager.reset() if hasattr(self.arc_manager, 'reset') else None
        self.plot_engine.reset() if hasattr(self.plot_engine, 'reset') else None
        self.scene_engine.reset() if hasattr(self.scene_engine, 'reset') else None


class DefaultArcManager:
    """Default arc manager when none is provided.

    This is a minimal implementation that does nothing.
    Replace with your actual arc management system.
    """

    def update(self, world_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Update arcs based on world state.

        Args:
            world_state: Current world state.

        Returns:
            List of active arcs (empty by default).
        """
        return []

    def reset(self) -> None:
        """Reset arc manager."""
        pass


class DefaultPlotEngine:
    """Default plot engine when none is provided.

    This is a minimal implementation that does nothing.
    Replace with your actual plot engine.
    """

    def select(
        self,
        arcs: List[Dict[str, Any]],
        player_intent: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Select the next narrative beat.

        Args:
            arcs: List of active story arcs.
            player_intent: The parsed player intent.

        Returns:
            Narrative beat dictionary.
        """
        return {
            "type": "default_beat",
            "description": "No plot engine provided",
            "arcs": arcs,
        }

    def reset(self) -> None:
        """Reset plot engine."""
        pass


class DefaultSceneEngine:
    """Default scene engine when none is provided.

    This is a minimal implementation that returns the beat as-is.
    Replace with your actual scene engine.
    """

    def generate(self, beat: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a scene from a narrative beat.

        Args:
            beat: The narrative beat to generate a scene for.

        Returns:
            Scene data dictionary.
        """
        return {
            "narrative": beat,
            "scene_data": {},
        }

    def reset(self) -> None:
        """Reset scene engine."""
        pass