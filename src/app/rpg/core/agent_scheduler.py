"""Agent Scheduler — Multi-agent orchestration for RPG simulation.

This module implements PATCH 2 from rpg-design.txt:
"Introduce Agent Scheduler"

The Problem: No true agent orchestration. Player drives everything.
The Solution: A scheduler that coordinates Director, Tools, Memory,
and Narrator in the correct order for each turn.

Architecture:
    run_turn(input) →
        1. Director decides (multi-step plan)
        2. Execute each action in plan
        3. Update memory with events
        4. Apply world state changes
        5. Generate narration
    
Usage:
    scheduler = AgentScheduler(director, registry, memory, narrator, world)
    result = scheduler.run_turn(session, player_input)

Design Compliance:
    - Multiple actions per turn
    - Multi-agent coordination
    - Order: Director → Actions → Memory → World → Narrator
    - Supports autonomous ticks (PATCH 3)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from rpg.story.director_agent import DirectorAgent, DirectorOutput
from rpg.tools.action_registry import ActionRegistry
from rpg.memory.memory_manager import MemoryManager
from rpg.narration.narrator import NarratorAgent
from rpg.world.world_state import WorldState


class AgentScheduler:
    """Coordinates multi-agent RPG simulation per turn.
    
    This is the central orchestrator that ensures all agents
    (Director, Actor, Memory, Narrator) work together in the
    correct order.
    
    Turn Flow:
    1. Director.decide() → multi-step plan
    2. For each action in plan:
        a. ActionRegistry.execute_action_dict()
        b. Collect events
    3. MemoryManager.add_events() with collected events
    4. WorldState.apply_event() for all events
    5. NarratorAgent.generate() with events
    6. Return result dict
    
    Attributes:
        director: DirectorAgent for story decisions.
        registry: ActionRegistry for action execution.
        memory: MemoryManager for memory updates.
        narrator: NarratorAgent for narration generation.
        world: WorldState for world state management.
    """
    
    def __init__(
        self,
        director: Optional[DirectorAgent] = None,
        registry: Optional[ActionRegistry] = None,
        memory: Optional[MemoryManager] = None,
        narrator: Optional[NarratorAgent] = None,
        world: Optional[WorldState] = None,
    ):
        """Initialize AgentScheduler.
        
        Args:
            director: DirectorAgent instance.
            registry: ActionRegistry instance.
            memory: MemoryManager instance.
            narrator: NarratorAgent instance.
            world: WorldState instance.
        """
        self.director = director or DirectorAgent()
        self.registry = registry or ActionRegistry()
        if world:
            self.registry.set_world(world)
        self.memory = memory
        self.narrator = narrator or NarratorAgent()
        self.world = world
        
        # Hook for session-dependent operations
        self._session = None
        
    def set_session(self, session: Any) -> None:
        """Set the game session for context-aware operations.
        
        Args:
            session: Game session object.
        """
        self._session = session
        
    def run_turn(
        self,
        session: Any,
        player_input: str,
        memory_context: str = "",
        beliefs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute one complete turn of the RPG simulation.
        
        This is the authoritative turn runner that coordinates all agents.
        
        Turn Flow:
        1. Director decides story direction (multi-step plan)
        2. Execute each action in the plan
        3. Apply world state changes
        4. Update memory with events
        5. Generate narrative output
        
        Args:
            session: Current game session.
            player_input: Player's input text.
            memory_context: Pre-built memory context string.
            beliefs: NPC beliefs for Director decision-making.
            
        Returns:
            Dict with:
            - narration: Generated narrative text
            - events: All events from this turn
            - plan: Director's plan explanation
            - reasoning: Director's reasoning
            - world: Updated world state summary
        """
        self._session = session
        all_events: List[Dict[str, Any]] = []
        
        # Step 1: Director decides story direction
        world = self.world or getattr(session, 'world', None)
        world_context = ""
        if hasattr(world, 'serialize_for_prompt'):
            world_context = world.serialize_for_prompt()
            
        director_output = self.director.decide(
            player_input=player_input,
            context="",
            world=world,
            memory_context=memory_context,
            beliefs=beliefs,
        )
        
        # Step 2: Execute each action in the plan
        for action_dict in director_output.actions:
            try:
                result = self.registry.execute_action_dict(action_dict)
                action_events = result.get("events", [])
                all_events.extend(action_events)
                
                # Apply events to world state
                for event in action_events:
                    self._apply_event_to_world(event)
            except Exception as e:
                # Log error but continue turn
                all_events.append({
                    "type": "error",
                    "action": action_dict.get("action", "unknown"),
                    "error": str(e),
                })
                
        # Step 3: Update memory with events
        if self.memory and all_events:
            current_tick = getattr(world, 'time', 0) if world else 0
            self.memory.add_events(all_events, current_tick=current_tick)
            
        # Step 4: Advance world time
        if world:
            world.advance_time()
            
        # Step 5: Generate narrative output
        narration = ""
        if all_events:
            narration = self.narrator.generate(all_events)
            
        # Build result
        return {
            "narration": narration,
            "events": all_events,
            "plan": director_output.plan,
            "reasoning": director_output.reasoning,
            "world": world.serialize_for_prompt() if world else "",
            "tension_delta": director_output.tension_delta,
        }
        
    def run_autonomous_turn(
        self,
        session: Any,
        memory_context: str = "",
        beliefs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an autonomous turn (no player input).
        
        Used when the Director triggers autonomous story beats
        or when the player is inactive.
        
        Args:
            session: Current game session.
            memory_context: Pre-built memory context.
            beliefs: NPC beliefs for Director decision-making.
            
        Returns:
            Same format as run_turn().
        """
        return self.run_turn(
            session=session,
            player_input="",
            memory_context=memory_context,
            beliefs=beliefs,
        )
        
    def execute_plan(
        self,
        plan: DirectorOutput,
        apply_to_world: bool = True,
        record_memory: bool = True,
    ) -> Dict[str, Any]:
        """Execute a pre-built DirectorOutput plan.
        
        Useful when the plan comes from an external source
        (e.g., saved plan, deterministic script).
        
        Args:
            plan: DirectorOutput to execute.
            apply_to_world: Whether to apply events to world.
            record_memory: Whether to record events in memory.
            
        Returns:
            Dict with events and narration.
        """
        all_events: List[Dict[str, Any]] = []
        
        for action_dict in plan.actions:
            try:
                result = self.registry.execute_action_dict(action_dict)
                action_events = result.get("events", [])
                all_events.extend(action_events)
                
                if apply_to_world:
                    for event in action_events:
                        self._apply_event_to_world(event)
            except Exception as e:
                all_events.append({
                    "type": "error",
                    "action": action_dict.get("action", "unknown"),
                    "error": str(e),
                })
                
        # Update memory
        if record_memory and self.memory and all_events:
            current_tick = getattr(self.world, 'time', 0) if self.world else 0
            self.memory.add_events(all_events, current_tick=current_tick)
            
        # Advance time
        if apply_to_world and self.world:
            self.world.advance_time()
            
        # Generate narration
        narration = ""
        if all_events:
            narration = self.narrator.generate(all_events)
            
        return {
            "narration": narration,
            "events": all_events,
            "plan": plan.plan,
            "reasoning": plan.reasoning,
        }
        
    def _apply_event_to_world(self, event: Dict[str, Any]) -> None:
        """Apply a single event to the world state.
        
        Args:
            event: Event dict to apply.
        """
        if self.world and hasattr(self.world, 'apply_event'):
            self.world.apply_event(event)
        elif self._session and hasattr(self._session, 'world'):
            if hasattr(self._session.world, 'apply_event'):
                self._session.world.apply_event(event)
                
    def reset(self) -> None:
        """Reset scheduler state."""
        self._session = None


class AutonomousTickManager:
    """Manages autonomous AI decisions during player inactivity.
    
    This implements PATCH 3 from rpg-design.txt:
    "Add Autonomous Tick System"
    
    The AI Director can:
    - Trigger events autonomously
    - Progress story without player input
    - Create scenes based on story needs
    
    Usage:
        tick_mgr = AutonomousTickManager(scheduler, session)
        if tick_mgr.should_tick(player_last_active, idle_threshold=60):
            result = tick_mgr.autonomous_tick()
    """
    
    def __init__(
        self,
        scheduler: AgentScheduler,
        session: Optional[Any] = None,
        default_interval: int = 5,
    ):
        """Initialize AutonomousTickManager.
        
        Args:
            scheduler: AgentScheduler to use for autonomous turns.
            session: Optional game session for context.
            default_interval: Default turns between autonomous ticks.
        """
        self.scheduler = scheduler
        self.session = session
        self.default_interval = default_interval
        self._tick_counter = 0
        self._last_tick_time = 0
        
    def should_tick(
        self,
        player_last_active: float = 0,
        current_time: float = 0,
        idle_threshold: float = 30.0,
    ) -> bool:
        """Check if an autonomous tick should be triggered.
        
        Triggers when:
        - Player has been inactive for idle_threshold seconds
        - OR enough turns have passed (default_interval)
        
        Args:
            player_last_active: Timestamp of last player activity.
            current_time: Current timestamp.
            idle_threshold: Seconds of inactivity to trigger tick.
            
        Returns:
            True if autonomous tick should fire.
        """
        # Check time-based trigger
        if current_time > 0 and player_last_active > 0:
            idle_time = current_time - player_last_active
            if idle_time >= idle_threshold:
                return True
                
        # Check turn-based trigger
        self._tick_counter += 1
        if self._tick_counter >= self.default_interval:
            self._tick_counter = 0
            return True
            
        return False
        
    def autonomous_tick(
        self,
        memory_context: str = "",
        beliefs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an autonomous story tick.
        
        The Director decides what happens next based on story state,
        without player input.
        
        Args:
            memory_context: Memory context for Director.
            beliefs: NPC beliefs for Director.
            
        Returns:
            Result dict from scheduler.
        """
        session = self.session
        if session is None:
            session = self.scheduler._session
            
        return self.scheduler.run_autonomous_turn(
            session=session,
            memory_context=memory_context,
            beliefs=beliefs,
        )
        
    def tick(self) -> Dict[str, Any]:
        """Alias for autonomous_tick()."""
        return self.autonomous_tick()
        
    def reset(self) -> None:
        """Reset tick manager state."""
        self._tick_counter = 0
        self._last_tick_time = 0