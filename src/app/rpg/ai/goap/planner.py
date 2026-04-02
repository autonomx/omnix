"""GOAP Planner — pure planning module with no side effects.

This module provides a deterministic GOAP planner that returns a structured
plan dict (goal, steps, priority) instead of executing actions directly.

The planner is designed to work as the deterministic backbone of the
DecisionEngine pipeline.
"""

from __future__ import annotations

from heapq import heappop, heappush
from typing import Any, Dict, List, Optional


class _Node:
    """Internal search node for GOAP planning."""

    def __init__(self, state: Dict[str, Any], cost: float, plan: List[Any]) -> None:
        self.state = state
        self.cost = cost
        self.plan = plan

    def __lt__(self, other: "_Node") -> bool:
        return self.cost < other.cost


class Action:
    """A GOAP action with preconditions and effects.

    This class replaces the old standalone ``Action`` by providing
    a cleaner interface with type hints.
    """

    def __init__(
        self,
        name: str,
        cost: float,
        preconditions: Dict[str, Any],
        effects: Dict[str, Any],
    ) -> None:
        self.name = name
        self.cost = cost
        self.preconditions = preconditions
        self.effects = effects

    def is_applicable(self, state: Dict[str, Any]) -> bool:
        """Check if this action can be applied in the given state.

        Args:
            state: The current world state dict.

        Returns:
            True if all preconditions are satisfied.
        """
        for k, v in self.preconditions.items():
            if state.get(k) != v:
                return False
        return True

    def apply(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Apply this action's effects to a state.

        Args:
            state: The current world state dict.

        Returns:
            A new state dict with effects applied.
        """
        new_state = dict(state)
        new_state.update(self.effects)
        return new_state


def _goal_satisfied(state: Dict[str, Any], goal: Dict[str, Any]) -> bool:
    """Check if the current state satisfies the goal conditions.

    Args:
        state: The current world state.
        goal: Desired goal state conditions.

    Returns:
        True if all goal conditions are met.
    """
    for k, v in goal.items():
        if state.get(k) != v:
            return False
    return True


def plan(
    initial_state: Dict[str, Any],
    goal: Dict[str, Any],
    actions: List[Any],
    max_depth: int = 5,
) -> List[Any]:
    """Find a sequence of actions to achieve a goal.

    This is the classic GOAP A* planner.  It returns a list of Action
    objects, NOT the execution result.

    Args:
        initial_state: The starting world state.
        goal: The desired goal state conditions.
        actions: The pool of available actions.
        max_depth: Maximum plan length to prevent infinite loops.

    Returns:
        A list of Action objects forming the plan, or an empty list
        if no plan could be found.
    """
    open_list: List[_Node] = []
    heappush(open_list, _Node(initial_state, 0, []))

    while open_list:
        node = heappop(open_list)

        if _goal_satisfied(node.state, goal):
            return node.plan

        if len(node.plan) >= max_depth:
            continue

        for action in actions:
            if action.is_applicable(node.state):
                new_state = action.apply(node.state)
                new_plan = node.plan + [action]
                new_cost = node.cost + action.cost
                heappush(open_list, _Node(new_state, new_cost, new_plan))

    return []


class GOAPPlanner:
    """Pure GOAP planner that returns a structured plan dict.

    Usage:
        planner = GOAPPlanner(actions)
        plan = planner.plan(npc, world_state)
        # plan is: {"goal": "...", "steps": [...], "priority": 0.8}
    """

    def __init__(self, actions: Optional[List[Action]] = None) -> None:
        """Initialise the planner.

        Args:
            actions: Pool of available actions.  If None, uses default actions.
        """
        self.actions = actions or _default_actions()

    def plan(self, npc: Any, world_state: Dict[str, Any]) -> Dict[str, Any]:
        """Compute a structured plan for the NPC.

        This method is pure — no side effects.  It returns a plan dict
        that can be evaluated by the LLM and resolved by the ActionResolver.

        Args:
            npc: The NPC entity to plan for.
            world_state: The current world state.

        Returns:
            A structured plan dict with keys:
                - ``goal`` (str): The primary goal name.
                - ``steps`` (list): List of action names to execute.
                - ``priority`` (float): Plan priority (0.0–1.0).
        """
        # Derive goals from NPC state and world state
        goals = self._derive_goals(npc, world_state)

        if not goals:
            return {"goal": "idle", "steps": ["idle"], "priority": 0.1}

        # Sort by priority and plan for the highest priority goal
        goals.sort(key=lambda g: g.get("priority", 0), reverse=True)

        best_plan: Dict[str, Any] = {
            "goal": "idle",
            "steps": ["idle"],
            "priority": 0.1,
        }
        best_priority = 0.1

        for goal_info in goals:
            goal_state = goal_info.get("conditions", {})
            plan_steps = plan(world_state, goal_state, self.actions)

            if plan_steps:
                step_names = [
                    a.name if hasattr(a, "name") else str(a) for a in plan_steps
                ]
                candidate = {
                    "goal": goal_info["name"],
                    "steps": step_names,
                    "priority": goal_info.get("priority", 0.5),
                }
                if goal_info["priority"] > best_priority:
                    best_plan = candidate
                    best_priority = goal_info["priority"]
                break  # Found a plan for the highest priority goal

        return best_plan

    def _derive_goals(
        self, npc: Any, world_state: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Derive NPC goals from state.

        Analyzes the NPC and world state to produce a list of candidate
        goals with priorities.

        Args:
            npc: The NPC entity.
            world_state: The current world state.

        Returns:
            List of goal dicts with ``name``, ``priority``, and
            ``conditions`` keys.
        """
        goals: List[Dict[str, Any]] = []

        # Survival goal (high priority when health is low)
        hp = getattr(npc, "hp", 100)
        if hp < 30:
            goals.append({
                "name": "survive",
                "priority": 0.95,
                "conditions": {"safe": True},
            })

        # Combat goal (when enemies are visible)
        if world_state.get("enemy_visible"):
            goals.append({
                "name": "combat",
                "priority": 0.85,
                "conditions": {"enemy_hp": "reduced"},
            })

        # Exploration goal (default)
        goals.append({
            "name": "explore",
            "priority": 0.3,
            "conditions": {"explored": True},
        })

        return goals


def _default_actions() -> List[Action]:
    """Internal default actions getter."""
    return [
        Action(
            name="attack",
            cost=2,
            preconditions={"enemy_visible": True, "target_in_range": True},
            effects={"enemy_hp": "reduced"},
        ),
        Action(
            name="move_to_target",
            cost=1,
            preconditions={"has_target": True, "target_in_range": False},
            effects={"target_in_range": True},
        ),
        Action(
            name="flee",
            cost=1,
            preconditions={"low_hp": True},
            effects={"safe": True},
        ),
        Action(
            name="approach",
            cost=1,
            preconditions={"enemy_visible": False, "has_target": True},
            effects={"enemy_visible": True},
        ),
        Action(
            name="idle",
            cost=3,
            preconditions={},
            effects={},
        ),
    ]


def default_actions() -> List[Action]:
    """Return default GOAP actions for NPCs.

    Returns:
        List of Action objects representing common NPC behaviors.
    """
    return [
        Action(
            name="attack",
            cost=2,
            preconditions={"enemy_visible": True, "target_in_range": True},
            effects={"enemy_hp": "reduced"},
        ),
        Action(
            name="move_to_target",
            cost=1,
            preconditions={"has_target": True, "target_in_range": False},
            effects={"target_in_range": True},
        ),
        Action(
            name="flee",
            cost=1,
            preconditions={"low_hp": True},
            effects={"safe": True},
        ),
        Action(
            name="approach",
            cost=1,
            preconditions={"enemy_visible": False, "has_target": True},
            effects={"enemy_visible": True},
        ),
        Action(
            name="idle",
            cost=3,
            preconditions={},
            effects={},
        ),
    ]


def build_memory_based_state(npc: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build GOAP state dict from NPC's memories and relationships.

    This creates memory-based preconditions that make planning
    context-aware.

    Args:
        npc: The NPC to build state for.
        context: Optional context dict to merge.

    Returns:
        State dict with memory-derived values.
    """
    state = dict(context) if context else {}

    # Default values
    state.setdefault("has_target", False)
    state.setdefault("enemy_visible", False)
    state.setdefault("target_in_range", False)
    state.setdefault("low_hp", getattr(npc, "hp", 100) < 30)
    state.setdefault("safe", True)
    state.setdefault("has_hostile_memory", False)
    state.setdefault("has_ally", False)
    state.setdefault("has_healer_nearby", False)

    # Memory-based preconditions
    memories = npc.memory.get("events", []) if isinstance(getattr(npc, "memory", None), dict) else []
    relationships = npc.memory.get("relationships", {}) if isinstance(getattr(npc, "memory", None), dict) else {}

    # Check for hostile memories (anyone with anger > 0.5 or damage events)
    hostile_targets: List[str] = []
    for target_id, rel in relationships.items():
        if rel.get("anger", 0) > 0.5:
            hostile_targets.append(target_id)

    # Also check for damage event patterns
    damage_sources: List[str] = []
    for mem in memories:
        if mem.get("type") == "damage" and mem.get("target") == getattr(npc, "id", None):
            source = mem.get("source", mem.get("actor", ""))
            if source and source not in damage_sources:
                damage_sources.append(source)

    hostile_targets.extend(damage_sources)
    # Deduplicate
    hostile_targets = list(set(hostile_targets))

    if hostile_targets:
        state["has_hostile_memory"] = True
        state["hostile_targets"] = hostile_targets

    # Check for ally relationships (trust > 0.5)
    allies: List[str] = []
    for target_id, rel in relationships.items():
        if rel.get("trust", 0) > 0.5:
            allies.append(target_id)

    if allies:
        state["has_ally"] = True
        state["allies"] = allies

    # Check for healing memories (potential healer allies)
    heal_sources: List[str] = []
    for mem in memories:
        if mem.get("type") == "heal" and mem.get("target") == getattr(npc, "id", None):
            source = mem.get("source", mem.get("actor", ""))
            if source and source not in heal_sources:
                heal_sources.append(source)

    if heal_sources:
        state["has_healer_nearby"] = True
        state["healers"] = heal_sources

    return state


def move_to_target(npc: Any, target: Any) -> Optional[Dict[str, Any]]:
    """Move NPC toward target using directional movement.

    Computes the direction vector and moves one step toward target.
    Uses Euclidean movement for smooth positioning.

    Args:
        npc: The NPC to move.
        target: The target entity to move toward.

    Returns:
        Event dict representing the move action, or None if already
        at target.
    """
    tx, ty = target.position
    x, y = npc.position

    dx = tx - x
    dy = ty - y

    step = 1.0
    dist = max(0.001, (dx**2 + dy**2) ** 0.5)

    # Already at target (within step distance)
    if dist <= step:
        return None

    # Move one step toward target
    npc.position = (
        x + (dx / dist) * step,
        y + (dy / dist) * step,
    )

    return {
        "type": "move",
        "source": npc.id,
        "target": target.id,
        "position": npc.position,
    }