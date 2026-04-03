"""PHASE 4.5 — Candidate Action Generator

Generates candidate action sequences for NPC planning simulation.

This module provides:
- CandidateGenerator: Creates 3-5 plausible NPC actions
- Filters by NPC state, goals, and world context
- Prevents invalid action generation

Example:
    generator = CandidateGenerator()
    candidates = generator.generate(npc, context={"goal": "attack"})
    # Returns [[Event("attack", target="goblin")], [Event("flee")], ...]
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from ...core.event_bus import Event

logger = logging.getLogger(__name__)


class ActionTemplate(Protocol):
    """Protocol for action templates."""

    def create_event(self, context: Dict[str, Any]) -> Event:
        """Create an event from this template with context.

        Args:
            context: Current world/NPC context.

        Returns:
            Event instance for simulation.
        """
        ...


@dataclass
class ActionOption:
    """A single action option for candidate generation.

    Attributes:
        name: Action type name (e.g., "attack", "flee", "talk").
        conditions: Dict of condition checks for applicability.
        priority: Higher priority actions generated first.
        create_event_fn: Optional custom event factory.
    """

    name: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: float = 1.0
    create_event_fn: Optional[Callable[[Dict[str, Any]], Event]] = None

    def is_applicable(self, context: Dict[str, Any]) -> bool:
        """Check if this action is applicable in the current context.

        Args:
            context: World/NPC context dictionary.

        Returns:
            True if action conditions are met.
        """
        for key, value in self.conditions.items():
            ctx_value = context.get(key)
            if ctx_value != value:
                return False
        return True

    def create_event(self, context: Dict[str, Any]) -> Event:
        """Create an event from this action option.

        Args:
            context: Current context for event parameters.

        Returns:
            Event instance.
        """
        if self.create_event_fn:
            return self.create_event_fn(context)

        # Default event creation
        return Event(
            type=self.name,
            payload={
                "actor": context.get("npc_id", "unknown_npc"),
                **{k: v for k, v in context.items() if k != "npc_id"},
            },
        )


# Default action options for common NPC behaviors
DEFAULT_ACTIONS = [
    ActionOption(
        name="attack",
        conditions={"has_target": True, "can_reach": True},
        priority=2.0,
    ),
    ActionOption(
        name="flee",
        conditions={"hp_low": True},
        priority=3.0,  # High priority when hurt
    ),
    ActionOption(
        name="move_to_target",
        conditions={"has_target": True, "can_reach": False},
        priority=1.5,
    ),
    ActionOption(
        name="talk",
        conditions={"has_ally": True, "can_reach": True},
        priority=1.0,
    ),
    ActionOption(
        name="heal",
        conditions={"hp_low": True, "has_healing": True},
        priority=2.5,
    ),
    ActionOption(
        name="wander",
        conditions={},  # Always applicable
        priority=0.5,
    ),
    ActionOption(
        name="observe",
        conditions={},  # Always applicable
        priority=0.3,
    ),
    ActionOption(
        name="defend",
        conditions={"has_ally": True, "ally_in_danger": True},
        priority=2.0,
    ),
]


class CandidateGenerator:
    """Generate candidate action sequences for NPC planning.

    This generator creates 3-5 plausible action sequences based on
    NPC state, goals, and world context. Actions are filtered by
    applicability conditions.

    Integration:
    - Called before NPCPlanner.choose_action()
    - Returns list of candidate event lists
    """

    def __init__(
        self,
        actions: Optional[List[ActionOption]] = None,
        max_candidates: int = 5,
    ):
        """Initialize the CandidateGenerator.

        Args:
            actions: Custom action options. Defaults to DEFAULT_ACTIONS.
            max_candidates: Maximum candidates to generate. Default 5.
        """
        self.actions = actions or DEFAULT_ACTIONS
        self.max_candidates = max_candidates

    def generate(
        self,
        npc_context: Dict[str, Any],
        world_context: Optional[Dict[str, Any]] = None,
    ) -> List[List[Event]]:
        """Generate candidate action sequences.

        Creates multiple plausible action sequences based on context.
        Each candidate is a single-event list for simple actions,
        or multi-event sequences for complex behaviors.

        Args:
            npc_context: NPC-specific context (hp, position, goals, etc.).
            world_context: Optional world state context.

        Returns:
            List of candidates, each being a list of Events.

        Example:
            candidates = generator.generate(
                npc_context={"npc_id": "warrior_1", "hp": 20, "has_target": True},
                world_context={"time": "night", "danger": True},
            )
            # Returns [[Event("attack")], [Event("flee")], [Event("heal")]]
        """
        combined = {**(world_context or {}), **npc_context}
        applicable = [a for a in self.actions if a.is_applicable(combined)]

        # If no applicable actions, return idle
        if not applicable:
            return [[Event(type="idle", payload={"actor": npc_context.get("npc_id", "unknown")})]]

        # Sort by priority (highest first)
        applicable.sort(key=lambda a: a.priority, reverse=True)

        # Create candidates from applicable actions
        candidates: List[List[Event]] = []
        for action in applicable[: self.max_candidates]:
            try:
                event = action.create_event(combined)
                candidates.append([event])
            except Exception as e:
                logger.warning(f"Failed to create event for {action.name}: {e}")

        # Ensure at least one candidate
        if not candidates:
            candidates.append(
                [Event(type="idle", payload={"actor": npc_context.get("npc_id", "unknown")})]
            )

        return candidates

    def generate_with_combos(
        self,
        npc_context: Dict[str, Any],
        world_context: Optional[Dict[str, Any]] = None,
        combo_length: int = 2,
    ) -> List[List[Event]]:
        """Generate candidates including action combinations.

        Creates both single actions and multi-action sequences
        for deeper planning.

        Args:
            npc_context: NPC context.
            world_context: Optional world context.
            combo_length: Length of action sequences to generate.

        Returns:
            List of candidates (single + combo).
        """
        combined = {**(world_context or {}), **npc_context}
        applicable = [a for a in self.actions if a.is_applicable(combined)]
        applicable.sort(key=lambda a: a.priority, reverse=True)

        candidates: List[List[Event]] = []

        # Single action candidates
        for action in applicable[: self.max_candidates]:
            try:
                event = action.create_event(combined)
                candidates.append([event])
            except Exception:
                pass

        # Combo candidates (action sequences)
        for action in applicable[:3]:  # Limit to top 3 for combos
            combo = []
            for _ in range(combo_length):
                try:
                    event = action.create_event(combined)
                    combo.append(event)
                except Exception:
                    break
            if len(combo) == combo_length:
                candidates.append(combo)

        return candidates[: self.max_candidates]

    def add_custom_action(
        self,
        name: str,
        conditions: Optional[Dict[str, Any]] = None,
        priority: float = 1.0,
        create_event_fn: Optional[Callable[[Dict[str, Any]], Event]] = None,
    ) -> None:
        """Add a custom action option.

        Args:
            name: Action type name.
            conditions: Applicability conditions.
            priority: Generation priority.
            create_event_fn: Custom event factory function.
        """
        self.actions.append(
            ActionOption(
                name=name,
                conditions=conditions or {},
                priority=priority,
                create_event_fn=create_event_fn,
            )
        )

    def clear_actions(self) -> None:
        """Clear all registered actions."""
        self.actions.clear()