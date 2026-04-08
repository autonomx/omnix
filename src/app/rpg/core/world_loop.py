"""World Simulation Loop v2 — Continuous tick with async NPC scheduling.

STEP 4 — World Simulation Loop: The missing backbone that turns
turn-based orchestration into a continuous, alive simulation.

HIGH-RISK GAP FIXES (2026-04-01):
1. Action Explosion Problem — Global action budget per tick
5. World Loop Runaway Complexity — Tick tiers for performance

The Problem: Current system is purely turn-based and waits for player input.
Without autonomous ticks, the world feels dead when the player is idle.

The Solution: A world_tick() function that runs the full simulation pipeline,
with asynchronous NPC scheduling (not all NPCs act every tick) and passive
world events that happen regardless of player action.

Architecture:
    world_tick() → [resources → npc_update → plan → resolve → execute →
                     world_apply → memory → arcs → passive_events]

Usage:
    loop = WorldSimulationLoop(world, npcs, director, ...)
    loop.world_tick()  # Call once per simulation tick

Key Features:
    - Core world_tick: Full simulation pipeline
    - Async NPC scheduling: NPCs act on different tick intervals
    - Passive world events: Weather, encounters, resource spawns
    - Tick counter and time tracking
    - Configurable tick rate (ticks per second)
    - [FIX #1] Global action budget to prevent explosion
    - [FIX #5] Tick tiers for O(N) performance management
"""

from __future__ import annotations

import random
from typing import Any, Callable, Dict, List, Optional

from rpg.core.npc_state import NPCState

# Default passive event probabilities
PASSIVE_EVENT_PROBABILITIES: Dict[str, float] = {
    "weather_change": 0.05,
    "wild_animal_appears": 0.03,
    "resource_spawn": 0.08,
    "stranger_encounter": 0.04,
    "rumor_spread": 0.06,
    "environmental_hazard": 0.02,
    "festival_begins": 0.01,
    "bandit_raid": 0.03,
}

# [FIX #1] Global action budget per tick
MAX_ACTIONS_PER_TICK = 20

# [FIX #5] Tick tier frequencies
TICK_TIER_CORE = 1       # Every tick: resources, npc_update, plan, resolve, execute
TICK_TIER_ARCS = 5       # Every 5 ticks: story arcs
TICK_TIER_PASSIVE = 10   # Every 10 ticks: passive events


class WorldSimulationLoop:
    """Continuous simulation loop with async NPC scheduling and passive events.
    
    Pipeline Order (per rpg-design.txt STEP 4):
    1. Update resources (regenerate)
    2. Update NPC internal states (emotions, threat assessment)
    3. Generate intentions (NPCs plan)
    4. Resolve conflicts (action resolver)
    5. Apply scene constraints
    6. Apply resource filters
    7. Execute with uncertainty
    8. Update world state
    9. Update story arcs
    10. Store memory
    11. Fire passive world events
    
    Attributes:
        tick: Current simulation tick counter.
        npcs: Dict of npc_id → NPCState.
        next_action_ticks: Dict of npc_id → next tick they can act.
        tick_min: Minimum ticks between NPC actions.
        tick_max: Maximum ticks between NPC actions.
        passive_events: Dict of event_name → probability.
    """
    
    def __init__(
        self,
        world: Any = None,
        npcs: Optional[Dict[str, NPCState]] = None,
        resource_manager: Any = None,
        resolver: Any = None,
        executor: Any = None,
        scene_manager: Any = None,
        memory_manager: Any = None,
        arc_manager: Any = None,
        director: Any = None,
        session: Any = None,
        tick_min: int = 1,
        tick_max: int = 3,
        passive_events: Optional[Dict[str, float]] = None,
        tick_callback: Optional[Callable[["WorldSimulationLoop"], None]] = None,
    ):
        """Initialize WorldSimulationLoop.
        
        Args:
            world: WorldState instance.
            npcs: Dict of npc_id → NPCState.
            resource_manager: ResourceManager instance.
            resolver: ActionResolver instance.
            executor: ProbabilisticActionExecutor instance.
            scene_manager: SceneManager instance.
            memory_manager: MemoryManager instance.
            arc_manager: StoryArcManager instance.
            director: Director instance.
            session: Game session.
            tick_min: Min ticks between NPC actions.
            tick_max: Max ticks between NPC actions.
            passive_events: Event name → probability dict.
            tick_callback: Optional callback fired after each tick.
        """
        self.world = world
        self.npcs = npcs or {}
        self.resource_manager = resource_manager
        self.resolver = resolver
        self.executor = executor
        self.scene_manager = scene_manager
        self.memory_manager = memory_manager
        self.arc_manager = arc_manager
        self.director = director
        self.session = session
        self.tick = 0
        self.tick_min = tick_min
        self.tick_max = tick_max
        self.passive_events = passive_events or dict(PASSIVE_EVENT_PROBABILITIES)
        self.tick_callback = tick_callback
        
        # Async NPC scheduling: npc_id → next tick they can act
        self.next_action_ticks: Dict[str, int] = {}
        for npc_id in self.npcs:
            self.next_action_ticks[npc_id] = self._schedule_next_tick()
            
        # Tick result
        self._last_tick_result: Dict[str, Any] = {}
        
    # ---------------------------------------------------------------
    # STEP 4: Core world_tick — The simulation backbone
    # ---------------------------------------------------------------
    
    def world_tick(self) -> Dict[str, Any]:
        """Execute one full simulation tick.
        
        [FIX #1] Action budget enforcement: Actions are limited to MAX_ACTIONS_PER_TICK.
        [FIX #5] Tick tiers: Arcs update every 5 ticks, passive events every 10 ticks.
        
        Returns:
            Tick result dict with events, npc_actions, passive_events.
        """
        self.tick += 1
        tick_events: List[Dict[str, Any]] = []
        npc_actions: List[Dict[str, Any]] = []
        passive_triggered: List[Dict[str, Any]] = []
        
        # Step 1: Update resources (every tick - core)
        tick_events.extend(self._step_resources())
        
        # Step 2: Update NPC internal states (every tick - core)
        tick_events.extend(self._step_npc_update())
        
        # Step 3: Generate intentions (NPCs plan actions)
        planned_actions = self._step_plan()
        
        # Step 4: Resolve conflicts
        resolved_actions = self._step_resolve(planned_actions)
        
        # Step 5: Apply scene constraints
        filtered_actions = self._step_scene_filter(resolved_actions)
        
        # Step 6: Apply resource filters
        affordable_actions = self._step_resource_filter(filtered_actions)
        
        # [FIX #1] Enforce global action budget before execution
        budgeted_actions = self.enforce_action_budget(affordable_actions)
        
        # Step 7: Execute with uncertainty
        exec_results = self._step_execute(budgeted_actions)
        tick_events.extend(self._collect_events(exec_results))
        for result in exec_results:
            npc_actions.append(result.get("action", {}))
        
        # Step 8: Update world state (every tick - core)
        self._step_world_apply(tick_events)
        
        # [FIX #5] Step 9: Update story arcs only on arc ticks (every 5 ticks)
        if self.is_arc_tick():
            arc_updates = self._step_arcs_update(tick_events)
        else:
            arc_updates = []
        
        # Step 10: Store memory (every tick - core for consistency)
        self._step_memory_store(tick_events)
        
        # [FIX #5] Step 11: Fire passive events only on passive ticks (every 10 ticks)
        if self.is_passive_tick():
            passive_triggered = self._step_passive_events()
            tick_events.extend(passive_triggered)
        
        # Tick callback
        if self.tick_callback:
            self.tick_callback(self)
            
        # [STEP 6 - Hook Into Existing World Loop]
        # Ensure events include structured fields for narrative conversion
        for e in tick_events:
            e.setdefault("description", e.get("type", "unknown event"))
            e.setdefault("actors", [])
        
        # Build result
        result = {
            "tick": self.tick,
            "events": tick_events,
            "npc_actions": npc_actions,
            "passive_events": passive_triggered,
            "active_npc_ids": self._get_active_npc_ids(),
            "budget_enforced": len(affordable_actions) > MAX_ACTIONS_PER_TICK,
            "actions_budgeted": len(affordable_actions),
            "actions_executed": len(budgeted_actions),
            "arc_tick": self.is_arc_tick(),
            "passive_tick": self.is_passive_tick(),
        }
        self._last_tick_result = result
        return result
        
    # ---------------------------------------------------------------
    # Pipeline step implementations
    # ---------------------------------------------------------------
    
    def _step_resources(self) -> List[Dict[str, Any]]:
        """Tick resource regeneration."""
        events = []
        if self.resource_manager and hasattr(self.resource_manager, "tick_all"):
            self.resource_manager.tick_all()
            events.append({"type": "resource_tick", "tick": self.tick})
        return events
        
    def _step_npc_update(self) -> List[Dict[str, Any]]:
        """Update NPC internal states (emotions, threat, progress).
        
        [FIX #4] Updates NPC tick counter for goal cooldown tracking.
        """
        events = []
        for npc_id, npc_state in self.npcs.items():
            if isinstance(npc_state, NPCState):
                # [FIX #4] Update NPC tick for cooldown tracking
                npc_state.update_tick(self.tick)
                
                npc_state.update_goal_progress(0.05)  # Small progress tick
                if npc_state.should_consider_new_goal():
                    # [FIX #4] Record goal use for cooldown
                    if npc_state.current_goal:
                        npc_state.record_goal_use(npc_state.current_goal.name)
                    npc_state.complete_current_goal()
                events.append({
                    "type": "npc_state_update",
                    "npc_id": npc_id,
                    "tick": self.tick,
                })
        return events
        
    def _step_plan(self) -> List[Dict[str, Any]]:
        """Generate planned actions from active NPCs."""
        actions = []
        for npc_id, npc_state in self.npcs.items():
            # STEP 4: Async scheduling — only NPCs whose tick has arrived
            if self.tick < self.next_action_ticks.get(npc_id, 0):
                continue
                
            if isinstance(npc_state, NPCState) and npc_state.current_goal:
                # Generate action from current goal
                goal = npc_state.current_goal
                action = {
                    "action": goal.name,
                    "npc_id": npc_id,
                    "parameters": goal.parameters,
                    "priority": goal.priority,
                    "intent_tick": self.tick,
                    "source": f"npc_{npc_id}",
                }
                actions.append(action)
                
            # Reschedule this NPC's next action tick
            self.next_action_ticks[npc_id] = self.tick + self._schedule_next_tick()
            
        # Director actions (always act every tick)
        if self.director:
            try:
                director_plan = self.director.get_planned_actions(
                    self.session, self.npcs
                )
                if isinstance(director_plan, list):
                    for action in director_plan:
                        action["intent_tick"] = self.tick
                        action["source"] = "director"
                        actions.append(action)
            except Exception:
                pass
                
        return actions
        
    def _step_resolve(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Resolve action conflicts."""
        if self.resolver and hasattr(self.resolver, "resolve"):
            return self.resolver.resolve(actions, world_state=self.world)
        return actions
        
    def _step_scene_filter(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter actions by scene constraints."""
        if self.scene_manager and hasattr(self.scene_manager, "filter_actions"):
            return self.scene_manager.filter_actions(actions)
        return actions
        
    def _step_resource_filter(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter by resource affordability."""
        if self.resource_manager and hasattr(self.resource_manager, "can_afford_action"):
            affordable = []
            for action in actions:
                npc_id = action.get("npc_id")
                action_type = action.get("action", "unknown")
                if npc_id and self.resource_manager.can_afford_action(npc_id, action_type):
                    affordable.append(action)
                elif not npc_id:
                    affordable.append(action)
            return affordable
        return actions
        
    def _step_execute(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute actions with uncertainty."""
        results = []
        for action in actions:
            if self.executor and hasattr(self.executor, "execute_with_uncertainty"):
                result = self.executor.execute_with_uncertainty(action)
            else:
                result = {
                    "success": True,
                    "action": action,
                    "events": [{"type": "action_executed", "action": action}],
                }
            results.append(result)
        return results
        
    def _collect_events(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collect events from execution results."""
        events = []
        for result in results:
            events.extend(result.get("events", []))
        return events
        
    def _step_world_apply(self, events: List[Dict[str, Any]]) -> None:
        """Apply events to world state."""
        if self.world and hasattr(self.world, "time"):
            self.world.time = getattr(self.world, "time", 0) + 1
            
    def _step_arcs_update(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Update story arcs."""
        updates = []
        if self.arc_manager and hasattr(self.arc_manager, "update_arcs"):
            updates = self.arc_manager.update_arcs(events)
        if self.director and hasattr(self.director, "update"):
            try:
                self.director.update(self.session, events)
            except Exception:
                pass
        return updates
        
    def _step_memory_store(self, events: List[Dict[str, Any]]) -> None:
        """Store events in memory."""
        if self.memory_manager and hasattr(self.memory_manager, "add_events"):
            self.memory_manager.add_events(events, current_tick=self.tick)
        
    # ---------------------------------------------------------------
    # STEP 4: Passive world events
    # ---------------------------------------------------------------
        
    def _step_passive_events(self) -> List[Dict[str, Any]]:
        """Fire passive world events based on probabilities.
        
        Returns:
            List of passive event dicts triggered this tick.
        """
        triggered = []
        for event_name, probability in self.passive_events.items():
            if random.random() < probability:
                event = {
                    "type": "passive_event",
                    "sub_type": event_name,
                    "tick": self.tick,
                    "data": self._generate_passive_event_data(event_name),
                }
                triggered.append(event)
        return triggered
        
    def _generate_passive_event_data(self, event_name: str) -> Dict[str, Any]:
        """Generate data for a passive event.
        
        Args:
            event_name: Name of the passive event.
            
        Returns:
            Event-specific data dict.
        """
        data: Dict[str, Any] = {}
        if event_name == "weather_change":
            weathers = ["clear", "rain", "storm", "fog", "snow"]
            data["new_weather"] = random.choice(weathers)
        elif event_name == "resource_spawn":
            data["resource_type"] = random.choice(["herb", "ore", "wood"])
            data["quantity"] = random.randint(1, 5)
        elif event_name == "stranger_encounter":
            data["stranger_type"] = random.choice(["merchant", "traveler", "refugee"])
        elif event_name == "rumor_spread":
            data["rumor"] = random.choice([
                "bandits on the road",
                "treasure in the ruins",
                "plague in the north",
                "new king crowned",
            ])
        elif event_name == "environmental_hazard":
            data["hazard"] = random.choice(["landslide", "flood", "fire", "quake"])
        return data
        
    # ---------------------------------------------------------------
    # STEP 4: Async NPC scheduling
    # ---------------------------------------------------------------
        
    def _schedule_next_tick(self) -> int:
        """Schedule next tick for an NPC.
        
        Returns:
            Number of ticks until NPC acts again.
        """
        return random.randint(self.tick_min, self.tick_max)
        
    def _get_active_npc_ids(self) -> List[str]:
        """Get list of NPCs that can act this tick.
        
        Returns:
            List of NPC IDs whose next_action_tick <= current tick.
        """
        return [
            npc_id for npc_id, next_tick in self.next_action_ticks.items()
            if self.tick >= next_tick
        ]
        
    # ---------------------------------------------------------------
    # Utility methods
    # ---------------------------------------------------------------
    
    def add_npc(self, npc_id: str, npc_state: NPCState) -> None:
        """Add an NPC to the simulation.
        
        Args:
            npc_id: NPC identifier.
            npc_state: NPCState instance.
        """
        self.npcs[npc_id] = npc_state
        self.next_action_ticks[npc_id] = self.tick + self._schedule_next_tick()
        
    def remove_npc(self, npc_id: str) -> None:
        """Remove an NPC from the simulation."""
        self.npcs.pop(npc_id, None)
        self.next_action_ticks.pop(npc_id, None)
        
    def set_passive_probability(self, event_name: str, probability: float) -> None:
        """Set the probability of a passive event.
        
        Args:
            event_name: Event identifier.
            probability: Probability [0, 1].
        """
        self.passive_events[event_name] = max(0.0, min(1.0, probability))
        
    def get_last_tick_result(self) -> Dict[str, Any]:
        """Get the result of the last tick.
        
        Returns:
            Last tick result dict, or empty dict.
        """
        return self._last_tick_result
        
    def get_stats(self) -> Dict[str, Any]:
        """Get simulation statistics.
        
        Returns:
            Stats dict with tick count, NPC count, etc.
        """
        return {
            "tick": self.tick,
            "total_npcs": len(self.npcs),
            "active_npcs": len(self._get_active_npc_ids()),
            "passive_event_count": len(self.passive_events),
        }
        
    # ---------------------------------------------------------------
    # [FIX #1] Action budget enforcement
    # ---------------------------------------------------------------
    
    @staticmethod
    def enforce_action_budget(
        actions: List[Dict[str, Any]],
        max_actions: int = MAX_ACTIONS_PER_TICK,
    ) -> List[Dict[str, Any]]:
        """Enforce global action budget per tick.
        
        Sorts actions by priority (descending) and truncates to max_actions.
        This prevents action explosion when many NPCs generate events simultaneously.
        
        Args:
            actions: List of action dicts to budget.
            max_actions: Maximum number of actions allowed per tick.
            
        Returns:
            Budgeted action list, sorted by priority and truncated.
        """
        if len(actions) <= max_actions:
            return actions
        return sorted(actions, key=lambda a: a.get("priority", 0), reverse=True)[:max_actions]
        
    # ---------------------------------------------------------------
    # [FIX #5] Tick tier helpers
    # ---------------------------------------------------------------
    
    def is_core_tick(self) -> bool:
        """Check if this tick should run core systems."""
        return self.tick % TICK_TIER_CORE == 0
        
    def is_arc_tick(self) -> bool:
        """Check if this tick should update story arcs."""
        return self.tick % TICK_TIER_ARCS == 0
        
    def is_passive_tick(self) -> bool:
        """Check if this tick should run passive events."""
        return self.tick % TICK_TIER_PASSIVE == 0
