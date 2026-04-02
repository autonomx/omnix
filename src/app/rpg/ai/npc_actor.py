"""NPC Actor Model for the Dynamic NPC Intent System.

This module provides the NPCActor dataclass that represents
stateful agents in the RPG world with goals, beliefs, and plans.

Tier 17.5 Patch: Adds persistent goals with state tracking and
goal merging capabilities.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NPCGoal:
    """Represents a persistent goal for an NPC.

    NPCGoal tracks goal state including progress, status,
    failure history, and target information.

    Usage:
        goal = NPCGoal(
            id="goal_1",
            type="undermine_player",
            priority=0.7,
            target="player_1"
        )
        goal.update_progress(0.2)
    """

    id: str
    type: str
    priority: float
    progress: float = 0.0
    status: str = "active"  # active | completed | failed | abandoned
    created_tick: int = 0
    failed_attempts: int = 0
    target: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_progress(self, amount: float) -> float:
        """Update goal progress.

        Args:
            amount: Progress delta (positive or negative).

        Returns:
            New progress value (clamped 0.0-1.0).
        """
        self.progress = max(0.0, min(1.0, self.progress + amount))
        if self.progress >= 1.0 and self.status == "active":
            self.status = "completed"
        return self.progress

    def record_failure(self) -> int:
        """Record a plan failure for this goal.

        Returns:
            Updated failure count.
        """
        self.failed_attempts += 1
        if self.failed_attempts >= 5:
            self.status = "failed"
        return self.failed_attempts

    def reset(self) -> None:
        """Reset goal for reattempt."""
        self.progress = 0.0
        self.failed_attempts = 0
        self.status = "active"

    def to_dict(self) -> Dict[str, Any]:
        """Convert goal to dictionary.

        Returns:
            Dictionary representation of the goal.
        """
        return {
            "id": self.id,
            "type": self.type,
            "priority": self.priority,
            "progress": self.progress,
            "status": self.status,
            "created_tick": self.created_tick,
            "failed_attempts": self.failed_attempts,
            "target": self.target,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NPCGoal":
        """Create goal from dictionary.

        Args:
            data: Dictionary with goal fields.

        Returns:
            NPCGoal instance.
        """
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data["type"],
            priority=data.get("priority", 0.5),
            progress=data.get("progress", 0.0),
            status=data.get("status", "active"),
            created_tick=data.get("created_tick", 0),
            failed_attempts=data.get("failed_attempts", 0),
            target=data.get("target"),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return (
            f"NPCGoal(id='{self.id}', type='{self.type}', "
            f"priority={self.priority:.2f}, status='{self.status}', "
            f"progress={self.progress:.2f})"
        )


@dataclass
class NPCActor:
    """Represents a stateful NPC agent in the world.

    NPCActor manages goals, beliefs, traits, and plans for
    non-player characters that drive autonomous behavior.

    Tier 17.5 Patch: Goals are now stateful NPCGoal objects
    with persistent identity and failure tracking.

    Usage:
        npc = NPCActor(id="1", name="Enemy", faction="A")
        npc.add_npc_goal(NPCGoal(type="undermine_player", priority=0.7))
    """

    id: str
    name: str
    faction: str

    # Stateful goals (Tier 17.5)
    goals: List[NPCGoal] = field(default_factory=list)
    # Legacy goal support (dict-based goals for backward compatibility)
    legacy_goals: List[Dict[str, Any]] = field(default_factory=list)

    beliefs: Dict[str, float] = field(default_factory=dict)
    traits: Dict[str, float] = field(default_factory=dict)

    current_plan: List[Dict[str, Any]] = field(default_factory=list)
    current_goal: Optional[NPCGoal] = None
    last_action_tick: int = 0

    # NPC relationship tracking (Tier 17.5 Patch 4)
    relationships: Dict[str, float] = field(default_factory=dict)
    # Failure memory (Tier 17.5 Patch 2)
    failure_memory: List[Dict[str, Any]] = field(default_factory=list)

    def add_goal(self, goal: Dict[str, Any]) -> None:
        """Add a goal to the NPC's goal list.

        For backward compatibility, this adds a dict goal that
        can coexist with NPCGoal objects in the goals list.

        Args:
            goal: Dict with 'type' and 'priority' keys.
        """
        self.goals.append(goal)  # type: ignore[arg-type]

    def add_npc_goal(self, goal: NPCGoal) -> None:
        """Add a stateful goal to the NPC's goal list.

        Args:
            goal: NPCGoal instance.
        """
        self.goals.append(goal)

    def clear_goals(self) -> None:
        """Clear all goals."""
        self.goals.clear()
        self.legacy_goals.clear()

    def clear_plan(self) -> None:
        """Clear current plan."""
        self.current_plan.clear()

    def update_belief(self, key: str, delta: float) -> float:
        """Update a belief value by a delta.

        Args:
            key: Belief key.
            delta: Change amount.

        Returns:
            New belief value.
        """
        current = self.beliefs.get(key, 0.0)
        new_value = current + delta
        self.beliefs[key] = new_value
        return new_value

    def get_trait(self, key: str, default: float = 0.5) -> float:
        """Get a trait value.

        Args:
            key: Trait key.
            default: Default value if not found.

        Returns:
            Trait value.
        """
        return self.traits.get(key, default)

    def get_belief(self, key: str, default: float = 0.0) -> float:
        """Get a belief value.

        Args:
            key: Belief key.
            default: Default value if not found.

        Returns:
            Belief value.
        """
        return self.beliefs.get(key, default)

    def select_highest_priority_goal(self) -> Optional[Dict[str, Any]]:
        """Select the highest priority goal.

        For backward compatibility, returns a dict representation
        of the highest priority goal.

        Returns:
            Highest priority goal dict, or None if no goals.
        """
        best_goal: Optional[Dict[str, Any]] = None
        best_priority = -1.0

        # Check dict goals (backward compat)
        for goal in self.goals:
            if isinstance(goal, dict):
                priority = goal.get("priority", 0)
                if priority > best_priority:
                    best_priority = priority
                    best_goal = goal

        # Check legacy goals
        for goal in self.legacy_goals:
            priority = goal.get("priority", 0)
            if priority > best_priority:
                best_priority = priority
                best_goal = goal

        # Check NPCGoal objects
        from .npc_actor import NPCGoal
        for goal in self.goals:
            if isinstance(goal, NPCGoal) and goal.status == "active":
                if goal.priority > best_priority:
                    best_priority = goal.priority
                    best_goal = goal.to_dict()

        return best_goal

    def select_best_active_goal(self) -> Optional[NPCGoal]:
        """Select the highest priority active stateful goal.

        Returns:
            Highest priority active NPCGoal, or None.
        """
        # Only consider NPCGoal objects with status attribute
        active_goals = [
            g for g in self.goals
            if isinstance(g, NPCGoal) and g.status == "active"
        ]
        if not active_goals:
            return None
        return max(active_goals, key=lambda g: g.priority)

    def get_relationship(self, npc_id: str, default: float = 0.0) -> float:
        """Get relationship value with another NPC.

        Args:
            npc_id: Other NPC's ID.
            default: Default value if no relationship exists.

        Returns:
            Relationship value (-1.0 to 1.0).
        """
        return self.relationships.get(npc_id, default)

    def update_relationship(self, npc_id: str, delta: float) -> float:
        """Update relationship with another NPC.

        Args:
            npc_id: Other NPC's ID.
            delta: Change amount.

        Returns:
            New relationship value (clamped -1.0 to 1.0).
        """
        current = self.relationships.get(npc_id, 0.0)
        new_value = max(-1.0, min(1.0, current + delta))
        self.relationships[npc_id] = new_value
        return new_value

    def record_failure(self, action: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Record an action failure for learning.

        Args:
            action: The failed action dict.
            context: Additional context about the failure.
        """
        self.failure_memory.append({
            "action": action,
            "context": context,
            "tick": context.get("tick", 0),
        })
        # Limit memory size
        if len(self.failure_memory) > 50:
            self.failure_memory = self.failure_memory[-50:]

    def get_similar_failures(self, action_type: str, window: int = 10) -> int:
        """Count similar recent failures.

        Args:
            action_type: Action type to search for.
            window: Number of recent failures to check.

        Returns:
            Count of similar failures.
        """
        recent = self.failure_memory[-window:]
        return sum(
            1 for f in recent
            if f.get("action", {}).get("type") == action_type
        )

    def __repr__(self) -> str:
        return f"NPCActor(id='{self.id}', name='{self.name}', faction='{self.faction}')"