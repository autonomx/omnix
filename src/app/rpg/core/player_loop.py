"""Player Loop — STEP 5 of RPG Design Implementation.

This module implements the PlayerLoop, which ties together all narrative
systems into the main game loop for player-driven gameplay.

Purpose:
    Implement the "missing link" — the main game loop that connects
    player input, world simulation, and narrative generation into
    a coherent play experience.

Architecture:
    Player Input → World Tick → Event Conversion → Scene Update → Narration

Pipeline:
    1. Inject player action into world
    2. Run world_simulation.tick()
    3. Convert raw events to NarrativeEvents
    4. Select focus events (most important)
    5. Update scene with focus events
    6. Generate narrative from scene + events

Usage:
    loop = PlayerLoop(world, director, scene_manager, narrator)
    result = loop.step("I attack the guard")
    print(result["narration"])

Design Compliance:
    - STEP 5: Player Loop from rpg-design.txt
    - Orchestrates all other narrative systems
    - Pure function: input → output, no side effects beyond world state
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from rpg.narrative.narrative_event import NarrativeEvent


class PlayerLoop:
    """Main game loop connecting player input to narrative output.
    
    The PlayerLoop orchestrates:
    1. Player action injection
    2. World simulation
    3. Event-to-narrative conversion
    4. Scene management
    5. Narrative generation
    
    It bridges the gap between the simulation engine and the
    storytelling layer, providing the core play experience.
    
    Attributes:
        world: World simulation or state object.
        director: NarrativeDirector for event conversion and scoring.
        scene_manager: SceneManager for scene tracking.
        narrator: Callable for narrative generation. Can be a
                  NarrativeGenerator, NarratorAgent, or any callable
                  that takes events and context and returns text.
    """
    
    def __init__(
        self,
        world: Any = None,
        director: Any = None,
        scene_manager: Any = None,
        narrator: Any = None,
        simulate_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    ):
        """Initialize the PlayerLoop.
        
        Args:
            world: WorldState or simulation object. If None, simulate_fn
                   must be provided.
            director: NarrativeDirector or equivalent with convert_events()
                      and select_focus_events() methods.
            scene_manager: SceneManager for tracking scene context.
            narrator: Callable or object with generate(event_list, context)
                      method. If callable, should take events+context.
            simulate_fn: Optional custom world tick function. Signature:
                         simulate_fn() -> list_of_event_dicts.
        """
        self.world = world
        self.director = director
        self.scene_manager = scene_manager
        self.narrator = narrator
        self.simulate_fn = simulate_fn
        self._last_result: Dict[str, Any] = {}
        
    def step(self, player_input: str) -> Dict[str, Any]:
        """Execute one complete game loop step.
        
        This is the main entry point. Takes player input and returns
        narrative output.
        
        Pipeline:
        1. Convert player input to world event
        2. Inject player event into world
        3. Run world simulation tick
        4. Convert raw events to narrative events
        5. Select focus events for narration
        6. Update scene
        7. Generate narrative
        
        Args:
            player_input: Raw text input from the player (e.g., "I attack").
            
        Returns:
            Result dict with keys:
            - narration: Generated narrative text
            - events: List of focus NarrativeEvents
            - scene_context: Current scene context
            - raw_events: Raw world events from simulation
        """
        # 1. Convert player input to world event
        player_event = self._convert_input(player_input)
        
        # 2. Inject player action into world
        if self.world:
            self._inject_player_event(player_event)
        
        # 3. Run world simulation tick
        world_events = self._simulate_tick()
        
        # Add player event to world events for context
        world_events.insert(0, player_event)
        
        # 4. Convert to narrative events
        if self.director:
            narrative_events = self.director.convert_events(world_events)
        else:
            # Fallback: create minimal narrative events
            narrative_events = [
                NarrativeEvent(
                    id=str(i),
                    type=e.get("type", "unknown"),
                    description=e.get("description", e.get("type", "event")),
                    actors=e.get("actors", []),
                    raw_event=e,
                )
                for i, e in enumerate(world_events)
            ]
        
        # 5. Select important ones
        if self.director:
            focus_events = self.director.select_focus_events(narrative_events)
        else:
            focus_events = narrative_events  # All events if no director
        
        # 6. Update scene
        if self.scene_manager:
            self.scene_manager.update_scene([e.raw_event for e in focus_events])
        
        scene_context = (
            self.scene_manager.get_scene_context()
            if self.scene_manager
            else {}
        )
        
        # 7. Generate narration
        narration = self._generate_narration(focus_events, scene_context)
        
        # Build result
        result = {
            "narration": narration,
            "events": focus_events,
            "scene_context": scene_context,
            "raw_events": world_events,
        }
        self._last_result = result
        return result
    
    def step_no_narration(self, player_input: str) -> Dict[str, Any]:
        """Execute game loop step without narrative generation.
        
        Useful for testing or when narration is handled externally.
        
        Args:
            player_input: Raw player input text.
            
        Returns:
            Result dict with events but no narration.
        """
        player_event = self._convert_input(player_input)
        world_events = self._simulate_tick()
        world_events.insert(0, player_event)
        
        if self.director:
            narrative_events = self.director.convert_events(world_events)
            focus_events = self.director.select_focus_events(narrative_events)
        else:
            focus_events = [
                NarrativeEvent(
                    id=str(i),
                    type=e.get("type", "unknown"),
                    description=e.get("description", ""),
                    actors=e.get("actors", []),
                    raw_event=e,
                )
                for i, e in enumerate(world_events)
            ]
        
        if self.scene_manager:
            self.scene_manager.update_scene([e.raw_event for e in focus_events])
        
        return {
            "narration": "",
            "events": focus_events,
            "scene_context": (
                self.scene_manager.get_scene_context()
                if self.scene_manager
                else {}
            ),
            "raw_events": world_events,
        }
        
    def _convert_input(self, text: str) -> Dict[str, Any]:
        """Convert player text input to world event dict.
        
        Args:
            text: Raw player input.
            
        Returns:
            Event dict representing the player action.
        """
        return {
            "type": "player_action",
            "description": text,
            "actors": ["player"],
        }
    
    def _inject_player_event(self, event: Dict[str, Any]) -> None:
        """Inject player event into the world simulation.
        
        Args:
            event: Player event dict to inject.
        """
        if hasattr(self.world, "inject_event"):
            self.world.inject_event(event)
        elif hasattr(self.world, "add_event"):
            self.world.add_event(event)
        # If world has no injection method, the event will still
        # be included in the result for narrative purposes
        
    def _simulate_tick(self) -> List[Dict[str, Any]]:
        """Run the world simulation tick.
        
        Returns:
            List of event dicts from the tick.
        """
        if self.simulate_fn:
            return self.simulate_fn()
        elif self.world and hasattr(self.world, "world_tick"):
            return self.world.world_tick()
        elif self.world and hasattr(self.world, "tick"):
            result = self.world.tick()
            if isinstance(result, list):
                return result
            return result.get("events", []) if isinstance(result, dict) else []
        else:
            return []
    
    def _generate_narration(
        self,
        focus_events: List[NarrativeEvent],
        scene_context: Dict[str, Any],
    ) -> str:
        """Generate narrative text from focus events and scene context.
        
        Args:
            focus_events: Selected narrative events for narration.
            scene_context: Scene context dict from the scene manager.
            
        Returns:
            Generated narrative text, or empty string if no narrator.
        """
        if not focus_events:
            return "Nothing of note happens."
        
        if self.narrator is None:
            return self._template_fallback(focus_events)
        
        # Try to use NarrativeGenerator style (generate method with events+context)
        if hasattr(self.narrator, "generate"):
            try:
                return self.narrator.generate(focus_events, scene_context)
            except TypeError:
                # Might be a different generator interface
                pass
        
        # Try generate_from_dicts for raw events
        if hasattr(self.narrator, "generate_from_dicts"):
            raw_events = [e.raw_event for e in focus_events]
            try:
                return self.narrator.generate_from_dicts(raw_events, scene_context)
            except Exception:
                pass
        
        # Try as a simple callable
        if callable(self.narrator):
            try:
                return self.narrator(focus_events)
            except TypeError:
                pass
        
        return self._template_fallback(focus_events)
    
    @staticmethod
    def _template_fallback(events: List[NarrativeEvent]) -> str:
        """Generate template fallback narrative when narrator is unavailable.
        
        Args:
            events: Narrative events to narrate.
            
        Returns:
            Template narrative text.
        """
        if not events:
            return "Nothing of note happens."
        
        sentences = []
        for event in events:
            sentences.append(event.description)
        
        return " ".join(sentences) if sentences else "Time passes."
    
    def get_last_result(self) -> Dict[str, Any]:
        """Get the result of the last step.
        
        Returns:
            Last step result dict, or empty dict if no step executed.
        """
        return self._last_result
        
    def reset(self) -> None:
        """Reset the player loop state."""
        self._last_result = {}
        if self.scene_manager and hasattr(self.scene_manager, "end_scene"):
            self.scene_manager.end_scene()
        if self.director and hasattr(self.director, "clear_buffer"):
            self.director.clear_buffer()