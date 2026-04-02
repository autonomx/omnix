"""Goal Engine with Lifecycle Management.

Patch 2: Goal Lifecycle
- Goals track completion state (active -> completed/failed)
- Progress increments based on matching events
- Completed goals are pruned from active list
- Summary includes completed/failed counts
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ActiveGoal:
    """Represents an active goal with progress tracking and lifecycle.

    Attributes:
        goal: The goal definition dict.
        progress: Float from 0.0 to 1.0 indicating completion.
        completed: Whether this goal has been completed.
        failed: Whether this goal has been abandoned/failed.
    """

    def __init__(self, goal: Dict[str, Any]):
        """Initialize an active goal.

        Args:
            goal: Goal dict with 'type', 'target', 'priority' keys.
        """
        self.goal = goal
        self.progress = 0.0
        self.completed = False
        self.failed = False

    @property
    def goal_type(self) -> str:
        """Return the goal type."""
        return self.goal.get("type", "unknown")

    @property
    def target(self) -> Optional[str]:
        """Return the goal target."""
        return self.goal.get("target")

    @property
    def priority(self) -> float:
        """Return the goal priority."""
        return self.goal.get("priority", 0.5)

    def advance(self, amount: float) -> None:
        """Advance goal progress.

        Args:
            amount: Amount to add to progress.
        """
        self.progress = min(1.0, max(0.0, self.progress + amount))
        if self.progress >= 1.0:
            self.completed = True

    def mark_failed(self) -> None:
        """Mark this goal as failed."""
        self.failed = True

    def to_dict(self) -> Dict[str, Any]:
        """Return dict representation.

        Returns:
            Dict with goal state fields.
        """
        return {
            "type": self.goal_type,
            "target": self.target,
            "priority": self.priority,
            "progress": self.progress,
            "completed": self.completed,
            "failed": self.failed,
            "raw_goal": self.goal,
        }

    def __repr__(self) -> str:
        return (
            f"ActiveGoal(type='{self.goal_type}', "
            f"progress={self.progress:.2f}, "
            f"completed={self.completed}, failed={self.failed})"
        )


class GoalEngine:
    """Manages NPC goals with lifecycle tracking and progress.

    Patch 2 additions:
    - Goals have completed/failed state
    - Events advance progress for matching goals
    - Completed goals are automatically pruned
    - Summary shows full lifecycle state
    """

    def __init__(self, npc_id: str = ""):
        """Initialize goal engine.

        Args:
            npc_id: NPC identifier.
        """
        self.npc_id = npc_id
        self.active_goals: List[ActiveGoal] = []
        self.completed_goals: List[ActiveGoal] = []
        self.failed_goals: List[ActiveGoal] = []

    def add_goal(self, goal: Dict[str, Any]) -> ActiveGoal:
        """Add a goal to the active pool.

        Args:
            goal: Goal dict with 'type', 'priority', etc.

        Returns:
            The created ActiveGoal wrapper.
        """
        ag = ActiveGoal(goal)
        self.active_goals.append(ag)
        return ag

    def add_goals(self, goals: List[Dict[str, Any]]) -> List[ActiveGoal]:
        """Add multiple goals at once.

        Args:
            goals: List of goal dicts.

        Returns:
            List of created ActiveGoal wrappers.
        """
        added = []
        for g in goals:
            added.append(self.add_goal(g))
        return added

    def update_progress(self, event: Dict[str, Any]) -> List[ActiveGoal]:
        """Update goal progress based on an event.

        Patch 2: Match events to goals and advance progress.
       复仇 events match revenge goals, attack events match attack goals, etc.

        Args:
            event: Event dict with 'type', 'target', 'actor' keys.

        Returns:
            List of goals that were completed by this event.
        """
        event_type = event.get("type", "")
        event_target = event.get("target", "")
        completed: List[ActiveGoal] = []

        for g in self.active_goals:
            if g.completed or g.failed:
                continue

            g_type = g.goal_type

            # Revenge goals advance on attack/damage to the target
            if g_type == "revenge" and event_type in ("attack", "damage", "kill"):
                if event_target == g.target:
                    g.advance(0.5)

            # Protect goals advance when threat is neutralized
            if g_type == "protect" and event_type in ("attack", "kill"):
                if event_target == g.target:
                    g.advance(0.3)

            # Generic: any goal with matching target type advances
            if g.target and event_target == g.target:
                g.advance(0.2)

            # Check for completion
            if g.progress >= 1.0 and not g.completed:
                g.completed = True
                completed.append(g)

        # Move completed goals
        for g in completed:
            self.active_goals.remove(g)
            self.completed_goals.append(g)

        return completed

    def prune(self) -> Dict[str, int]:
        """Remove completed/failed goals from active list.

        Returns:
            Dict with counts of pruned goals.
        """
        stats: Dict[str, int] = {"completed": 0, "failed": 0, "pruned": 0}

        still_active: List[ActiveGoal] = []
        for g in self.active_goals:
            if g.completed:
                self.completed_goals.append(g)
                stats["completed"] += 1
                stats["pruned"] += 1
            elif g.failed:
                self.failed_goals.append(g)
                stats["failed"] += 1
                stats["pruned"] += 1
            else:
                still_active.append(g)

        self.active_goals = still_active
        return stats

    def clear_resolved(self) -> None:
        """Remove completed/failed goals from active list.

        Patch 2: Lifecycle cleanup - only keep non-resolved goals.
        """
        self.active_goals = [g for g in self.active_goals if not g.completed and not g.failed]
        for g in self.active_goals[:]:
            if g.completed:
                self.completed_goals.append(g)
            elif g.failed:
                self.failed_goals.append(g)
        self.active_goals = [g for g in self.active_goals if not g.completed and not g.failed]

    def summarize(self) -> Dict[str, Any]:
        """Return a summary of goal state.

        Returns:
            Dict with active, completed, failed counts and details.
        """
        return {
            "active_count": len(self.active_goals),
            "completed_count": len(self.completed_goals),
            "failed_count": len(self.failed_goals),
            "active": [g.to_dict() for g in self.active_goals],
            "completed": [g.to_dict() for g in self.completed_goals[:5]],
            "failed": [g.to_dict() for g in self.failed_goals[:5]],
        }

    def get_highest_priority(self) -> Optional[ActiveGoal]:
        """Return the highest priority active goal.

        Returns:
            ActiveGoal with highest priority, or None.
        """
        if not self.active_goals:
            return None
        return max(self.active_goals, key=lambda g: g.priority)

    def has_goal_type(self, goal_type: str) -> bool:
        """Check if a goal type is active.

        Args:
            goal_type: Goal type to search for.

        Returns:
            True if an active goal of that type exists.
        """
        return any(g.goal_type == goal_type and not g.completed and not g.failed for g in self.active_goals)

    def reset(self) -> None:
        """Clear all goals."""
        self.active_goals.clear()
        self.completed_goals.clear()
        self.failed_goals.clear()

    def __repr__(self) -> str:
        return (
            f"GoalEngine(npc='{self.npc_id}', "
            f"active={len(self.active_goals)}, "
            f"completed={len(self.completed_goals)}, "
            f"failed={len(self.failed_goals)})"
        )