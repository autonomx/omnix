"""NPC State Manager v2 — Intent systems with utility scoring and interrupts.

STEP 3 — NPC Agency Upgrade: NPCs move from reactive goals to decision-grade
intent systems with utility scoring, personality modifiers, and interrupt handling.

The Problem: NPCs react per turn and don't pursue goals over time.
Without persistent intent, NPCs feel reactive, not alive.

The Solution: NPCs evaluate goals using utility formulas, can be interrupted
by high-priority events, and have personality modifiers that bias decisions.

Architecture:
    NPCState + Personality → UtilityEvaluator → GoalSelector → InterruptSystem

Usage:
    npc = NPCState("guard", personality={"aggression": 0.8, "fear": 0.2})
    npc.evaluate_goals(available_goals)  # Selects best goal via utility
    npc.check_interrupt(threat_level=0.9)  # May push flee goal

Key Features:
    - Utility scoring with configurable formula
    - Personality modifiers that bias utility
    - Interrupt system for threat response
    - Persistent goals across turns
    - Goal history for memory integration
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional


# [FIX #4] Goal cooldown to prevent feedback loops
GOAL_COOLDOWN_TICKS = 5
GOAL_COOLDOWN_PENALTY = 0.2  # Utility multiplier when on cooldown


class Personality:
    """Personality traits that bias NPC decision-making.
    
    Traits are floats in [0, 1] that modify utility scores.
    
    Attributes:
        aggression: Bias toward combat/attack actions.
        fear: Bias toward flee/defensive actions.
        loyalty: Bias toward protecting allies.
        curiosity: Bias toward exploration/investigation.
        greed: Bias toward resource gathering.
        sociability: Bias toward dialogue/alliance actions.
    """
    
    def __init__(
        self,
        aggression: float = 0.5,
        fear: float = 0.5,
        loyalty: float = 0.5,
        curiosity: float = 0.5,
        greed: float = 0.5,
        sociability: float = 0.5,
    ):
        self.aggression = max(0.0, min(1.0, aggression))
        self.fear = max(0.0, min(1.0, fear))
        self.loyalty = max(0.0, min(1.0, loyalty))
        self.curiosity = max(0.0, min(1.0, curiosity))
        self.greed = max(0.0, min(1.0, greed))
        self.sociability = max(0.0, min(1.0, sociability))
        
    def modify_utility(
        self,
        utility: float,
        goal_type: str,
    ) -> float:
        """Apply personality modifier to a goal's utility score.
        
        Args:
            utility: Base utility score.
            goal_type: Category of goal being evaluated.
            
        Returns:
            Modified utility score.
        """
        modifier = 1.0
        
        if goal_type in ("attack", "hunt", "combat"):
            modifier += self.aggression
        elif goal_type in ("flee", "defend", "hide"):
            modifier += self.fear
        elif goal_type in ("protect", "ally", "heal_ally"):
            modifier += self.loyalty
        elif goal_type in ("explore", "investigate", "observe"):
            modifier += self.curiosity
        elif goal_type in ("gather", "steal", "trade"):
            modifier += self.greed
        elif goal_type in ("talk", "negotiate", "befriend"):
            modifier += self.sociability
            
        return utility * modifier
        
    def to_dict(self) -> Dict[str, float]:
        """Serialize to dict."""
        return {
            "aggression": self.aggression,
            "fear": self.fear,
            "loyalty": self.loyalty,
            "curiosity": self.curiosity,
            "greed": self.greed,
            "sociability": self.sociability,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "Personality":
        """Create from dict."""
        return cls(
            aggression=data.get("aggression", 0.5),
            fear=data.get("fear", 0.5),
            loyalty=data.get("loyalty", 0.5),
            curiosity=data.get("curiosity", 0.5),
            greed=data.get("greed", 0.5),
            sociability=data.get("sociability", 0.5),
        )


# Default personality templates
PERSONALITY_TEMPLATES: Dict[str, Dict[str, float]] = {
    "aggressive_warrior": {"aggression": 0.9, "fear": 0.1, "loyalty": 0.7},
    "cautious_scout": {"aggression": 0.3, "fear": 0.8, "curiosity": 0.8},
    "greedy_merchant": {"greed": 0.9, "sociability": 0.7, "fear": 0.3},
    "friendly_healer": {"sociability": 0.9, "loyalty": 0.8, "aggression": 0.1},
    "loner_hermit": {"aggression": 0.6, "sociability": 0.1, "fear": 0.5},
}


class GoalState:
    """A single goal being pursued by an NPC."""
    
    def __init__(
        self,
        name: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: float = 1.0,
        urgency: float = 0.5,
        emotional_drive: float = 0.0,
        context_match: float = 0.5,
        max_stalled_ticks: int = 5,
    ):
        self.name = name
        self.parameters = parameters or {}
        self.priority = priority
        self.urgency = urgency
        self.emotional_drive = emotional_drive
        self.context_match = context_match
        self.progress = 0.0
        self.created_at = time.time()
        self._last_progress = 0.0
        self.stalled_ticks = 0
        self.max_stalled_ticks = max_stalled_ticks
        
    @property
    def utility_score(self) -> float:
        """Calculate utility score for this goal.
        
        Utility Formula:
            utility = (priority * 0.4) + (urgency * 0.3) +
                      (emotional_drive * 0.2) + (context_match * 0.1)
        """
        return (
            (self.priority * 0.4) +
            (self.urgency * 0.3) +
            (self.emotional_drive * 0.2) +
            (self.context_match * 0.1)
        )
        
    def apply_personality(self, personality: Personality) -> float:
        """Apply personality modifier and return adjusted utility.
        
        Args:
            personality: NPC personality.
            
        Returns:
            Personality-adjusted utility score.
        """
        goal_type = self.parameters.get("type", self.name.split("_")[0])
        return personality.modify_utility(self.utility_score, goal_type)
        
    def update(self, delta: float) -> None:
        """Update goal progress."""
        if delta > 0:
            self.progress = min(1.0, self.progress + delta)
            self.stalled_ticks = 0
        else:
            self.stalled_ticks += 1
            
    def is_complete(self) -> bool:
        return self.progress >= 1.0
        
    def is_blocked(self) -> bool:
        return self.stalled_ticks >= self.max_stalled_ticks
        
    def get_target(self) -> Optional[str]:
        return self.parameters.get("target")
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "parameters": self.parameters,
            "priority": self.priority,
            "progress": round(self.progress, 3),
            "stalled_ticks": self.stalled_ticks,
            "utility_score": round(self.utility_score, 3),
        }


class NPCState:
    """Persistent state with utility-driven goal selection and interrupts.
    
    [FIX #4] Added goal cooldown tracking to prevent feedback loops:
    attack → threat rises → flee → reset → attack → repeat
    
    Attributes:
        npc_id: The NPC this state belongs to.
        personality: Personality trait modifiers.
        current_goal: The goal being pursued.
        goal_stack: Ordered goals (can switch when blocked).
        goal_history: Past goals for memory integration.
        last_action: What the NPC did last turn.
        interrupt_threshold: Threat level that triggers interrupt.
        threat_level: Current perceived threat.
        goal_cooldowns: Dict of goal_name → last_used_tick (for cooldown).
        current_tick: Current simulation tick for cooldown calculation.
    """
    
    def __init__(
        self,
        npc_id: str,
        personality: Optional[Personality] = None,
        interrupt_threshold: float = 0.8,
        goal_cooldown_ticks: int = GOAL_COOLDOWN_TICKS,
    ):
        self.npc_id = npc_id
        self.personality = personality or Personality()
        self.current_goal: Optional[GoalState] = None
        self.goal_stack: List[GoalState] = []
        self.goal_history: List[Dict[str, Any]] = []
        self.last_action: Optional[str] = None
        self.intent_locked = False
        self._lock_duration = 3
        self.interrupt_threshold = interrupt_threshold
        self.threat_level = 0.0
        self._pending_interrupts: List[GoalState] = []
        # [FIX #4] Goal cooldown tracking
        self.goal_cooldowns: Dict[str, int] = {}  # goal_name → last_used_tick
        self.current_tick = 0
        self.goal_cooldown_ticks = goal_cooldown_ticks
        
    # ---------------------------------------------------------------
    # STEP 3: Utility-based goal evaluation
    # ---------------------------------------------------------------
    
    # ---------------------------------------------------------------
    # [FIX #4] Goal cooldown system
    # ---------------------------------------------------------------
    
    def update_tick(self, current_tick: int) -> None:
        """Update NPC's internal tick counter for cooldown tracking.
        
        [FIX #4] Call this each world tick to update cooldown timers.
        
        Args:
            current_tick: Current simulation tick.
        """
        self.current_tick = current_tick
        
    def is_goal_on_cooldown(self, goal_name: str) -> bool:
        """Check if a goal is currently on cooldown.
        
        [FIX #4] Prevents rapid goal cycling like attack→flee→attack.
        
        Args:
            goal_name: Goal identifier to check.
            
        Returns:
            True if goal is on cooldown.
        """
        last_used = self.goal_cooldowns.get(goal_name)
        if last_used is None:
            return False
        return (self.current_tick - last_used) < self.goal_cooldown_ticks
        
    def get_cooldown_remaining(self, goal_name: str) -> int:
        """Get remaining cooldown ticks for a goal.
        
        Args:
            goal_name: Goal identifier.
            
        Returns:
            Ticks remaining (0 if not on cooldown).
        """
        last_used = self.goal_cooldowns.get(goal_name)
        if last_used is None:
            return 0
        remaining = self.goal_cooldown_ticks - (self.current_tick - last_used)
        return max(0, remaining)
        
    def record_goal_use(self, goal_name: str) -> None:
        """Record that a goal was used, starting its cooldown.
        
        Call this after a goal is selected.
        
        Args:
            goal_name: Goal that was selected.
        """
        self.goal_cooldowns[goal_name] = self.current_tick
        
    def evaluate_goals(
        self,
        available_goals: List[Dict[str, Any]],
    ) -> Optional[GoalState]:
        """Evaluate available goals and select the best one.
        
        [FIX #4] Applies cooldown penalty to goals that were recently used,
        preventing feedback loops like attack → flee → attack → repeat.
        
        Each goal dict should have:
            - name: Goal identifier
            - priority: Base priority (0-10)
            - urgency: Current urgency (0-1)
            - emotional_drive: Emotional intensity (0-1)
            - context_match: How well the goal fits context (0-1)
            - type: Goal type for personality matching
            - parameters: Goal-specific parameters
            
        Args:
            available_goals: List of candidate goal dicts.
            
        Returns:
            Best GoalState, or None.
        """
        if not available_goals:
            return None
            
        # Skip evaluation if intent is locked
        if self.intent_locked:
            return self.current_goal
            
        candidates: List[GoalState] = []
        for goal_data in available_goals:
            goal = GoalState(
                name=goal_data.get("name", "unknown"),
                parameters=goal_data.get("parameters", {}),
                priority=goal_data.get("priority", 1.0),
                urgency=goal_data.get("urgency", 0.5),
                emotional_drive=goal_data.get("emotional_drive", 0.0),
                context_match=goal_data.get("context_match", 0.5),
            )
            
            # [FIX #4] Apply cooldown penalty
            if self.is_goal_on_cooldown(goal.name):
                goal.priority *= GOAL_COOLDOWN_PENALTY
                
            # Apply personality modifier
            adjusted = goal.apply_personality(self.personality)
            goal.priority = adjusted  # Store adjusted priority
            candidates.append(goal)
            
        if not candidates:
            return None
            
        # Select highest utility
        best = max(candidates, key=lambda g: g.utility_score)
        return best
        
    def set_goal(
        self,
        name: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: float = 1.0,
        push: bool = False,
    ) -> GoalState:
        """Set the NPC's current goal.
        
        [FIX #4] Records goal usage for cooldown tracking when a goal is set.
        """
        # Record previous goal's cooldown before switching
        if self.current_goal:
            self.record_goal_use(self.current_goal.name)
            if push:
                self.goal_stack.append(self.current_goal)
            else:
                self.goal_history.append({
                    "goal": self.current_goal.name,
                    "progress": self.current_goal.progress,
                    "completed": self.current_goal.is_complete(),
                })
            
        new_goal = GoalState(
            name=name,
            parameters=parameters,
            priority=priority,
        )
            
        self.current_goal = new_goal
        self.intent_locked = False
        return new_goal
        
    def select_goal(
        self,
        available_goals: List[Dict[str, Any]],
        push: bool = False,
    ) -> Optional[GoalState]:
        """Evaluate and select the best goal, optionally pushing to stack.
        
        [FIX #4] Records goal usage for cooldown tracking when a goal is selected,
        preventing feedback loops like attack→flee→attack→repeat.
        
        Args:
            available_goals: Candidate goal dicts.
            push: If True, push current goal to stack.
            
        Returns:
            Selected goal or None.
        """
        best = self.evaluate_goals(available_goals)
        if not best:
            return None
            
        # [FIX #4] Record previous goal's cooldown before switching
        if self.current_goal:
            self.record_goal_use(self.current_goal.name)
            if push:
                self.goal_stack.append(self.current_goal)
            else:
                self.goal_history.append({
                    "goal": self.current_goal.name,
                    "progress": self.current_goal.progress,
                    "completed": self.current_goal.is_complete(),
                })
            
        # Record the newly selected goal's usage to start its cooldown
        self.record_goal_use(best.name)
        
        self.current_goal = best
        self.intent_locked = False
        return best
        
    # ---------------------------------------------------------------
    # STEP 3: Interrupt system
    # ---------------------------------------------------------------
    
    def update_threat(self, threat_level: float) -> Optional[GoalState]:
        """Update threat assessment and check for interrupts.
        
        Args:
            threat_level: Current threat level (0-1).
            
        Returns:
            Interrupt goal if triggered, else None.
        """
        self.threat_level = max(0.0, min(1.0, threat_level))
        return self.check_interrupt()
        
    def check_interrupt(self) -> Optional[GoalState]:
        """Check if current threat level warrants an interrupt.
        
        Returns:
            Flee GoalState if_interrupt triggered, else None.
        """
        if self.threat_level >= self.interrupt_threshold:
            interrupt_goal = GoalState(
                name="flee",
                parameters={"reason": "high_threat", "threat_level": self.threat_level},
                priority=10.0,  # Maximum priority
                urgency=1.0,
                emotional_drive=1.0,
            )
            self._pending_interrupts.append(interrupt_goal)
            return interrupt_goal
        return None
        
    def process_interrupts(self) -> Optional[GoalState]:
        """Process pending interrupts, pushing highest priority one.
        
        Returns:
            Active interrupt goal, or None.
        """
        if not self._pending_interrupts:
            return None
            
        # Process highest threat interrupt
        self._pending_interrupts.sort(
            key=lambda g: g.parameters.get("threat_level", 0), reverse=True
        )
        interrupt = self._pending_interrupts.pop(0)
        
        if self.current_goal:
            self.goal_stack.append(self.current_goal)
        self.current_goal = interrupt
        self.intent_locked = True  # Lock intent during flee
        
        return interrupt
        
    def add_interrupt(
        self,
        goal_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: float = 10.0,
    ) -> None:
        """Manually add an interrupt goal.
        
        Args:
            goal_name: Interrupt goal name.
            parameters: Goal parameters.
            priority: Interrupt priority (default 10 = max).
        """
        interrupt = GoalState(
            name=goal_name,
            parameters=parameters,
            priority=priority,
        )
        self._pending_interrupts.append(interrupt)
        
    def clear_interrupts(self) -> None:
        """Clear all pending interrupts."""
        self._pending_interrupts.clear()
        
    # ---------------------------------------------------------------
    # Standard goal management
    # ---------------------------------------------------------------
    
    def update_goal_progress(self, delta: float) -> None:
        """Update current goal progress."""
        if self.current_goal:
            self.current_goal.update(delta)
            
    def get_goal_summary(self) -> str:
        """Get goal summary for LLM prompt injection."""
        if not self.current_goal:
            return "No current goal"
        g = self.current_goal
        return (
            f"Current Goal: {g.name} "
            f"(progress: {int(g.progress * 100)}%, "
            f"utility: {g.utility_score:.2f}, "
            f"target: {g.get_target() or 'none'})"
        )
        
    def should_consider_new_goal(self) -> bool:
        """Check if NPC should reconsider its goal."""
        if not self.current_goal:
            return True
        if self.current_goal.is_complete():
            return True
        if self.current_goal.is_blocked():
            return True
        return False
        
    def complete_current_goal(self) -> Optional[GoalState]:
        """Complete and archive the current goal."""
        if not self.current_goal:
            return None
            
        completed = self.current_goal
        self.goal_history.append({
            "goal": completed.name,
            "progress": completed.progress,
            "completed": True,
        })
        
        if self.goal_stack:
            self.current_goal = self.goal_stack.pop()
        else:
            self.current_goal = None
            
        self.intent_locked = False
        return completed
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "npc_id": self.npc_id,
            "current_goal": self.current_goal.to_dict() if self.current_goal else None,
            "goal_stack": [g.to_dict() for g in self.goal_stack],
            "goal_history": self.goal_history[-10:],
            "last_action": self.last_action,
            "personality": self.personality.to_dict(),
            "threat_level": self.threat_level,
            "pending_interrupts": len(self._pending_interrupts),
        }