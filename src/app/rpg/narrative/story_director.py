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
import copy

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
        coherence_core: Optional[Any] = None,
    ):
        """Initialize the StoryDirector.

        Args:
            arc_manager: Story arc manager. If None, uses DefaultArcManager.
            plot_engine: Plot engine for beat selection. If None, uses DefaultPlotEngine.
            scene_engine: Scene engine for scene generation. If None, uses DefaultSceneEngine.
            coherence_core: Optional CoherenceCore instance.
        """
        self.arc_manager = arc_manager or DefaultArcManager()
        self.plot_engine = plot_engine or DefaultPlotEngine()
        self.scene_engine = scene_engine or DefaultSceneEngine()
        self.coherence_core = coherence_core

        self.creator_canon_state = None
        self.gm_directive_state = None
        self._event_log: List[Dict[str, Any]] = []
        self._tick_count = 0
        self.mode: str = "live"

        # Phase 7.8 — Arc steering context (bias/guidance, not authority)
        self.arc_control_context: Dict[str, Any] | None = None

    def set_coherence_core(self, coherence_core: Any) -> None:
        self.coherence_core = coherence_core

    def set_creator_canon_state(self, creator_canon_state: Any) -> None:
        self.creator_canon_state = creator_canon_state

    def set_gm_directive_state(self, gm_directive_state: Any) -> None:
        self.gm_directive_state = gm_directive_state

    def set_recovery_manager(self, recovery_manager: Any) -> None:
        """Accept a recovery manager reference (Phase 6.5).

        The director does not own recovery state; it merely holds a
        reference so that the game loop can inject it if needed.
        """
        self._recovery_manager = recovery_manager

    def set_arc_control_context(self, context: Dict[str, Any] | None) -> None:
        """Accept arc steering context (Phase 7.8).

        The director consumes this as guidance — it does NOT become
        a truth owner.  Arc control context includes active arcs,
        due reveals, active pacing plan, and active scene bias.
        """
        self.arc_control_context = context

    def process(
        self,
        events: List[Event],
        player_intent: Dict[str, Any],
        event_bus: Any,
        coherence_context: Optional[Dict[str, Any]] = None,
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
        coherence_context = coherence_context or self._build_coherence_context()
        world_state = self._analyze(events, coherence_context=coherence_context)
        world_state["creator"] = self._build_creator_context()
        world_state["gm"] = self._build_gm_context()
        world_state["arc_control"] = self._build_arc_guidance()

        # 2. Update story arcs
        active_arcs = self.arc_manager.update(world_state)

        # 3. Select next narrative beat
        try:
            next_beat = self.plot_engine.select(active_arcs, player_intent, coherence_context=coherence_context)
        except TypeError:
            next_beat = self.plot_engine.select(active_arcs, player_intent)

        if isinstance(next_beat, dict):
            next_beat.setdefault("coherence", coherence_context)

        # Emit narrative beat selected event (structured event type)
        event_bus.emit(Event(
            "narrative_beat_selected",
            {
                "beat": next_beat,
                "coherence_scene_summary": coherence_context.get("scene_summary", {}),
                "unresolved_thread_count": len(coherence_context.get("unresolved_threads", [])),
                "tick": self._tick_count,
            },
            source="story_director"
        ))

        # 4. Generate scene
        try:
            scene = self.scene_engine.generate(next_beat, coherence_context=coherence_context)
        except TypeError:
            scene = self.scene_engine.generate(next_beat)

        if isinstance(scene, dict):
            scene.setdefault("coherence", coherence_context)

        # Emit scene_generated event with enhanced payload
        event_bus.emit(Event(
            "scene_generated",
            {
                "tick": self._tick_count,
                "beat": next_beat,
                "scene": scene,
                "coherence_scene_summary": coherence_context.get("scene_summary", {}),
            },
            source="story_director"
        ))

        return scene

    def _build_coherence_context(self) -> Dict[str, Any]:
        if self.coherence_core is None:
            return {
                "scene_summary": {},
                "active_tensions": [],
                "unresolved_threads": [],
                "recent_consequences": [],
                "last_good_anchor": None,
                "contradictions": [],
            }
        return {
            "scene_summary": self.coherence_core.get_scene_summary(),
            "active_tensions": self.coherence_core.get_active_tensions(),
            "unresolved_threads": self.coherence_core.get_unresolved_threads(),
            "recent_consequences": self.coherence_core.get_recent_consequences(limit=5),
            "last_good_anchor": self.coherence_core.get_last_good_anchor(),
            "contradictions": [
                c.to_dict()
                for c in self.coherence_core.get_state().contradictions[-10:]
            ],
        }

    def _build_creator_context(self) -> Dict[str, Any]:
        if self.creator_canon_state is None:
            return {}
        return self.creator_canon_state.serialize_state()

    def _build_gm_context(self) -> Dict[str, Any]:
        if self.gm_directive_state is None:
            return {}
        return self.gm_directive_state.build_director_context()

    def _build_arc_guidance(self) -> Dict[str, Any]:
        """Build arc steering guidance from the current arc control context.

        Phase 7.8: The director consumes active arcs, due reveals, active
        pacing plan, and active scene bias as guidance — not authority.
        """
        if self.arc_control_context is None:
            return {}
        return dict(self.arc_control_context)

    def _analyze(self, events: List[Event], coherence_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            "coherence": coherence_context or {},
            "event_count": len(events),
            "tick": self._tick_count,
        }

    def serialize_state(self) -> Dict[str, Any]:
        return {
            "tick_count": self._tick_count,
            "event_log": copy.deepcopy(self._event_log),
            "mode": self.mode,
        }

    def deserialize_state(self, data: Dict[str, Any]) -> None:
        self._tick_count = data.get("tick_count", 0)
        self._event_log = copy.deepcopy(data.get("event_log", []))
        self.mode = data.get("mode", "live")

    def set_mode(self, mode: str) -> None:
        self.mode = mode

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