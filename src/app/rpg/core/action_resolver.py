"""Action Resolver v2 — Deterministic simulation arbiter with temporal + causal resolution.

STEP 1 — Conflict Resolution 2.0: Upgraded from simple conflict handler to
a deterministic simulation arbiter that ensures predictable behavior under load.

The Problem: Multiple agents can act on the same entity, contradict each other,
or overwrite world state. Without temporal/causal ordering, execution is arbitrary.

The Solution: Sort actions by intent time + reaction time, apply causal blocking,
then resolve soft conflicts using action-type categories.

Architecture:
    planned_actions → sort_by_timeline → causal_block → soft_resolve → resolved_actions

Usage:
    resolver = ActionResolver()
    resolver.resolve(planned_actions, world_state)

Key Features:
    - Temporal sorting: actions ordered by intent_tick, reaction_time, priority
    - Causal blocking: invalidated actions fail when preconditions no longer hold
    - Soft conflicts: stackable actions coexist, exclusive actions compete
    - Override actions: terminal actions (kill, escape) supersede all others
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set
from enum import Enum


class ResolutionStrategy(Enum):
    """Strategy for resolving conflicts between actions on the same target."""
    FIRST_WINS = "first_wins"
    HIGHEST_PRIORITY = "highest_priority"
    DIRECTOR_OVERRIDE = "director_override"
    RANDOM = "random"


# STEP 1: Soft conflict types — not all conflicts are binary
CONFLICT_TYPES: Dict[str, List[str]] = {
    "exclusive": ["move", "pick_up", "drop", "equip", "use_item", "block", "parry"],
    "stackable": ["attack", "heal", "buff", "debuff", "observe", "shield", "taunt"],
    "override": ["kill", "escape", "flee", "surrender", "teleport", "revive"],
}


def get_conflict_type(action_name: str) -> str:
    """Get the conflict category for an action.
    
    Args:
        action_name: Action identifier.
        
    Returns:
        Conflict type: 'exclusive', 'stackable', or 'override'.
    """
    for category, actions in CONFLICT_TYPES.items():
        if action_name in actions:
            return category
    return "exclusive"  # Default to exclusive


class ActionResolver:
    """Deterministic simulation arbiter with temporal + causal resolution.
    
    Resolution Pipeline:
    1. Sort actions by intent_tick, reaction_time, priority
    2. Apply causal blocking based on world state
    3. Group by target
    4. Apply soft conflict resolution
    5. Return resolved actions
    
    Attributes:
        strategy: Base resolution strategy.
        max_actions_per_target: Max actions per target for exclusive conflicts.
        log_resolutions: If True, logs resolution decisions.
    """
    
    def __init__(
        self,
        strategy: ResolutionStrategy = ResolutionStrategy.DIRECTOR_OVERRIDE,
        max_actions_per_target: int = 1,
        director_action_priority: float = 10.0,
        log_resolutions: bool = False,
    ):
        self.strategy = strategy
        self.max_actions_per_target = max_actions_per_target
        self.director_action_priority = director_action_priority
        self.log_resolutions = log_resolutions
        self._resolution_log: List[Dict[str, Any]] = []
        
    def resolve(
        self,
        planned_actions: List[Dict[str, Any]],
        world_state: Any = None,
        session: Any = None,
    ) -> List[Dict[str, Any]]:
        """Resolve conflicts with temporal + causal ordering.
        
        Args:
            planned_actions: List of action dicts from all agents.
            world_state: Optional world state for causal blocking.
            session: Optional game session.
            
        Returns:
            List of resolved, validated actions.
        """
        if not planned_actions:
            return []
            
        # Filter invalid
        valid_actions = [
            a for a in planned_actions
            if a.get("action") and a.get("npc_id")
            and not a.get("invalidated")
        ]
        if not valid_actions:
            return []
            
        # Sort by temporal ordering
        self._sort_by_timeline(valid_actions)
        
        # Assign priorities
        self._assign_priorities(valid_actions)
        
        # Causal blocking
        if world_state:
            self._apply_causal_effects(valid_actions, world_state)
            valid_actions = [a for a in valid_actions if not a.get("invalidated")]
        
        # Group by target
        target_groups = self._group_by_target(valid_actions)
        
        # Resolve per target
        resolved: List[Dict[str, Any]] = []
        for target, actions in target_groups.items():
            if target is None:
                resolved.extend(actions)
            else:
                resolved.extend(self._resolve_target_group(actions, target))
                
        if self.log_resolutions and self._resolution_log:
            import json
            log_summary = json.dumps(self._resolution_log, indent=2)
            print(f"[ActionResolver] Resolutions:\n{log_summary}")
            self._resolution_log.clear()
            
        return resolved
        
    # ---------------------------------------------------------------
    # STEP 1: Temporal sorting by intent time + reaction time
    # ---------------------------------------------------------------
    
    def _sort_by_timeline(self, actions: List[Dict[str, Any]]) -> None:
        """Sort actions by intent time, reaction speed, then priority.
        
        Sorting order:
        1. intent_tick (earlier intent first)
        2. reaction_time (lower = faster, goes first)
        3. priority (higher priority breaks ties)
        
        Args:
            actions: Actions to sort (in-place).
        """
        actions.sort(key=lambda a: (
            a.get("intent_tick", 0),
            a.get("reaction_time", 1.0),
            -a.get("priority", 0),
        ))
        
    # ---------------------------------------------------------------
    # STEP 1: Causal blocking
    # ---------------------------------------------------------------
    
    def _apply_causal_effects(
        self,
        actions: List[Dict[str, Any]],
        world_state: Any,
    ) -> None:
        """Apply causal blocking based on world state changes.
        
        Actions that are invalidated by prior actions in the same tick
        are marked as invalidated and removed from execution queue.
        
        Args:
            actions: Sorted actions to validate.
            world_state: World state for validation.
        """
        for action in actions:
            if action.get("invalidated"):
                continue
            if self._is_action_invalid(action, world_state):
                action["invalidated"] = True
                action["invalidation_reason"] = "causal_block"
                self._resolution_log.append({
                    "action": action.get("action"),
                    "npc_id": action.get("npc_id"),
                    "target": self._get_target(action),
                    "reason": "causal_block",
                    "detail": self._get_invalidation_detail(action, world_state),
                })
                
    def _is_action_invalid(self, action: Dict[str, Any], world_state: Any) -> bool:
        """Check if an action is invalid given the current world state.
        
        Args:
            action: Action to validate.
            world_state: World state.
            
        Returns:
            True if action should be blocked.
        """
        action_name = action.get("action", "")
        target = self._get_target(action)
        
        if not target:
            return False
            
        # Check if target exists
        if hasattr(world_state, "get_entity"):
            entity = world_state.get_entity(target)
            if entity is None:
                return True
                
        # Check if target is alive
        if hasattr(world_state, "is_alive"):
            if not world_state.is_alive(target):
                if action_name not in ("revive", "loot"):
                    return True
                    
        # Check if action is blocked by world constraints
        if hasattr(world_state, "is_blocked"):
            return world_state.is_blocked(action_name, target)
            
        return False
        
    def _get_invalidation_detail(self, action: Dict[str, Any], world_state: Any) -> str:
        """Get detail about why an action was invalidated."""
        target = self._get_target(action)
        if hasattr(world_state, "is_alive") and target:
            if not world_state.is_alive(target):
                return f"target '{target}' is not alive"
        return "world state conflict"
        
    # ---------------------------------------------------------------
    # Priority assignment
    # ---------------------------------------------------------------
    
    def _assign_priorities(self, actions: List[Dict[str, Any]]) -> None:
        """Assign priority scores to actions."""
        for action in actions:
            if "priority" not in action:
                source = action.get("source", "")
                if source == "director":
                    action["priority"] = self.director_action_priority
                else:
                    action["priority"] = 1.0
                    
    # ---------------------------------------------------------------
    # Grouping
    # ---------------------------------------------------------------
    
    def _group_by_target(
        self, actions: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group actions by their target entity."""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for action in actions:
            target = self._get_target(action)
            if target not in groups:
                groups[target] = []
            groups[target].append(action)
        return groups
        
    # ---------------------------------------------------------------
    # Soft conflict resolution
    # ---------------------------------------------------------------
    
    def _resolve_target_group(
        self,
        actions: List[Dict[str, Any]],
        target: str,
    ) -> List[Dict[str, Any]]:
        """Resolve all actions targeting a single entity using soft conflicts.
        
        Args:
            actions: All actions targeting the same entity.
            target: Target entity ID.
            
        Returns:
            Resolved actions.
        """
        if not actions:
            return []
            
        # Separate by conflict type
        override_actions = []
        stackable_actions = []
        exclusive_actions = []
        
        for action in actions:
            ctype = get_conflict_type(action.get("action", ""))
            if ctype == "override":
                override_actions.append(action)
            elif ctype == "stackable":
                stackable_actions.append(action)
            else:
                exclusive_actions.append(action)
                
        result: List[Dict[str, Any]] = []
        
        # Override actions win — everything else is dropped
        if override_actions:
            best = self._pick_best(override_actions)
            result.append(best)
            self._resolution_log.append({
                "target": target,
                "kept": best.get("action"),
                "dropped": [a.get("action") for a in actions if a is not best],
                "reason": "override",
            })
            return result
            
        # Stackable actions all coexist
        result.extend(stackable_actions)
        
        # Exclusive actions: pick best one
        if exclusive_actions:
            best = self._pick_best(exclusive_actions)
            result.append(best)
            if len(exclusive_actions) > 1:
                self._resolution_log.append({
                    "target": target,
                    "kept": best.get("action"),
                    "dropped": [a.get("action") for a in exclusive_actions if a is not best],
                    "reason": "exclusive",
                })
                
        return result
        
    def _pick_best(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Pick the best action from a group.
        
        Args:
            actions: Candidate actions.
            
        Returns:
            The winning action.
        """
        if len(actions) == 1:
            return actions[0]
            
        if self.strategy == ResolutionStrategy.HIGHEST_PRIORITY:
            return max(actions, key=lambda a: a.get("priority", 0))
        elif self.strategy == ResolutionStrategy.DIRECTOR_OVERRIDE:
            director_actions = [a for a in actions if a.get("source") == "director"]
            if director_actions:
                return max(director_actions, key=lambda a: a.get("priority", 0))
            return max(actions, key=lambda a: a.get("priority", 0))
        elif self.strategy == ResolutionStrategy.RANDOM:
            import random
            return random.choice(actions)
        else:
            return actions[0]  # FIRST_WINS
            
    # ---------------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------------
    
    def _get_target(self, action: Dict[str, Any]) -> Optional[str]:
        """Extract target from action."""
        return action.get("parameters", {}).get("target")


def create_default_resolver() -> ActionResolver:
    """Create a default ActionResolver with Step 1 settings."""
    return ActionResolver(
        strategy=ResolutionStrategy.DIRECTOR_OVERRIDE,
        max_actions_per_target=1,
        director_action_priority=10.0,
    )