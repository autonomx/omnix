"""Story Arc / Payoff Engine — TIER 9: Narrative Intelligence Layer.

This module implements the Story Arc Engine from Tier 9 of the RPG design specification.

Purpose:
    Track long-term narrative arcs with setup → payoff structure.
    Complete arcs when world state satisfies payoff conditions.

The Problem:
    - Events are isolated, not building toward anything
    - No long-term narrative threads or foreshadowing
    - Player actions don't have delayed consequences
    - Story lacks dramatic structure

The Solution:
    StoryArcEngine manages StoryArc objects that:
    - Have setup events that initiate the arc
    - Track arc progress through world state changes
    - Complete when payoff conditions are met
    - Generate payoff events when arcs resolve

Usage:
    engine = StoryArcEngine()
    
    # Register a war arc
    engine.register_arc(StoryArc(
        id="war_mages_warriors",
        setup="War breaks out between Mages and Warriors",
        payoff_condition=lambda ws: ws.get("war_duration", 0) > 10,
        payoff="After 10 turns of war, exhaustion sets in"
    ))
    
    # Each tick
    completed = engine.update(world_state)

Architecture:
    Arc Registration → World State Monitoring → Payoff Detection → Arc Completion
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class StoryArc:
    """A long-term narrative arc with setup and payoff structure.
    
    StoryArcs track multi-turn narrative threads that build toward
    dramatic payoffs. They have conditions that determine when
    the arc reaches its climax/resolution.
    
    Attributes:
        id: Unique arc identifier.
        description: Setup description of the arc.
        payoff_condition: Callable that checks if arc is complete.
        payoff_description: Description of completed arc payoff.
        completed: Whether arc has been resolved.
        metadata: Additional arc data.
        created_tick: Tick when arc was created.
        completed_tick: Tick when arc was completed (if resolved).
    """
    
    id: str
    description: str
    payoff_condition: Callable[[Dict[str, Any]], bool]
    payoff_description: str = "The arc reaches its conclusion."
    completed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_tick: int = 0
    completed_tick: Optional[int] = None
    
    def complete(self, current_tick: int) -> Dict[str, Any]:
        """Mark the arc as completed.
        
        Args:
            current_tick: Current simulation tick.
            
        Returns:
            Completed arc data dict.
        """
        self.completed = True
        self.completed_tick = current_tick
        
        return {
            "type": "story_arc_complete",
            "arc_id": self.id,
            "description": self.description,
            "payoff": self.payoff_description,
            "duration": current_tick - self.created_tick,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict.
        
        Returns:
            Arc data as dictionary.
        """
        return {
            "id": self.id,
            "description": self.description,
            "payoff_description": self.payoff_description,
            "completed": self.completed,
            "created_tick": self.created_tick,
            "completed_tick": self.completed_tick,
            "metadata": dict(self.metadata),
        }


class StoryArcEngine:
    """Manages story arcs with setup → payoff structure.
    
    The StoryArcEngine tracks long-term narrative threads and detects
    when world conditions satisfy arc completion. Completed arcs
    generate payoff events that feed into the narrative system.
    
    Integration Points:
        - PlayerLoop.step(): update called each tick with world state
        - Plot Engine: Arcs can be registered from plot events
        - Narrative Memory: Completed arcs stored for continuity
    
    Usage:
        engine = StoryArcEngine()
        
        # Register arcs
        engine.register_arc(StoryArc(
            id="rising_tension",
            setup="Tensions rising between factions",
            payoff_condition=lambda ws: ws.get("tension", 0) > 0.8,
            payoff="Tensions explode into open conflict"
        ))
        
        # Each tick
        completed_arcs = engine.update(world_state)
    """
    
    def __init__(self):
        """Initialize the StoryArcEngine."""
        self.arcs: List[StoryArc] = []
        self.completed_arcs: List[StoryArc] = []
        self._arc_registry: Dict[str, StoryArc] = {}
    
    def register_arc(self, arc: StoryArc) -> None:
        """Register a new story arc.
        
        Args:
            arc: StoryArc to track.
        """
        self.arcs.append(arc)
        self._arc_registry[arc.id] = arc
    
    def register_arc_simple(
        self,
        arc_id: str,
        setup: str,
        payoff_condition: Callable[[Dict[str, Any]], bool],
        payoff_description: str = "The arc reaches its conclusion.",
        metadata: Optional[Dict[str, Any]] = None,
        current_tick: int = 0,
    ) -> StoryArc:
        """Register a story arc with simple parameters.
        
        Convenience method for creating arcs inline.
        
        Args:
            arc_id: Unique arc identifier.
            setup: Setup description.
            payoff_condition: Callable for completion check.
            payoff_description: Payoff description.
            metadata: Additional arc data.
            current_tick: Current simulation tick.
            
        Returns:
            Created StoryArc object.
        """
        arc = StoryArc(
            id=arc_id,
            description=setup,
            payoff_condition=payoff_condition,
            payoff_description=payoff_description,
            metadata=metadata or {},
            created_tick=current_tick,
        )
        self.register_arc(arc)
        return arc
    
    def update(self, world_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check all incomplete arcs for completion.
        
        Args:
            world_state: Current world state dict.
            
        Returns:
            List of payoff events for completed arcs.
        """
        completed_results: List[Dict[str, Any]] = []
        current_tick = world_state.get("tick", 0)
        
        still_incomplete: List[StoryArc] = []
        
        for arc in self.arcs:
            try:
                if arc.payoff_condition(world_state):
                    result = arc.complete(current_tick)
                    self.completed_arcs.append(arc)
                    completed_results.append(result)
                else:
                    still_incomplete.append(arc)
            except Exception:
                # If payoff condition errors, keep arc incomplete
                still_incomplete.append(arc)
        
        self.arcs = still_incomplete
        return completed_results
    
    def get_arc(self, arc_id: str) -> Optional[StoryArc]:
        """Get an arc by ID from active or completed arcs.
        
        Args:
            arc_id: Arc identifier.
            
        Returns:
            StoryArc or None if not found.
        """
        # Check active arcs first
        for arc in self.arcs:
            if arc.id == arc_id:
                return arc
        
        # Check completed arcs
        for arc in self.completed_arcs:
            if arc.id == arc_id:
                return arc
        
        return None
    
    def get_active_arcs(self) -> List[StoryArc]:
        """Get all active (incomplete) arcs.
        
        Returns:
            List of active StoryArc objects.
        """
        return list(self.arcs)
    
    def get_completed_arcs(self) -> List[StoryArc]:
        """Get all completed arcs.
        
        Returns:
            List of completed StoryArc objects.
        """
        return list(self.completed_arcs)
    
    def remove_arc(self, arc_id: str) -> bool:
        """Remove an arc regardless of completion state.
        
        Args:
            arc_id: Arc to remove.
            
        Returns:
            True if arc was found and removed.
        """
        for i, arc in enumerate(self.arcs):
            if arc.id == arc_id:
                self.arcs.pop(i)
                self._arc_registry.pop(arc_id, None)
                return True
        
        for i, arc in enumerate(self.completed_arcs):
            if arc.id == arc_id:
                self.completed_arcs.pop(i)
                self._arc_registry.pop(arc_id, None)
                return True
        
        return False
    
    def get_arc_summary(self) -> Dict[str, Any]:
        """Get summary of all arcs.
        
        Returns:
            Dict with active and completed arc counts and lists.
        """
        return {
            "active_arcs": len(self.arcs),
            "completed_arcs": len(self.completed_arcs),
            "active": [arc.to_dict() for arc in self.arcs],
            "completed": [arc.to_dict() for arc in self.completed_arcs],
        }
    
    def reset(self) -> None:
        """Clear all arc data."""
        self.arcs.clear()
        self.completed_arcs.clear()
        self._arc_registry.clear()


# ============================================================
# Pre-built arc factory functions for common narrative patterns
# ============================================================


def create_war_arc(factions: List[str], duration_threshold: int = 10) -> StoryArc:
    """Create a war arc that completes after sustained conflict.
    
    Args:
        factions: Faction IDs involved in the war.
        duration_threshold: Number of ticks until war exhaustion.
        
    Returns:
        Configured StoryArc for the war.
    """
    faction_str = " and ".join(factions)
    
    def payoff_condition(ws: Dict[str, Any]) -> bool:
        # Check if war has been ongoing long enough
        war_duration = ws.get("war_duration", {}).get(tuple(factions), 0)
        return war_duration >= duration_threshold
    
    return StoryArc(
        id=f"war_{'_'.join(factions)}",
        description=f"War erupts between {faction_str}",
        payoff_condition=payoff_condition,
        payoff_description=f"After {duration_threshold} turns of war, both sides are exhausted",
        metadata={"factions": factions, "type": "war"},
    )


def create_crisis_arc(location: str, good: str, severity_threshold: float = 0.9) -> StoryArc:
    """Create a crisis arc that completes when crisis is resolved or worsens.
    
    Args:
        location: Location experiencing the crisis.
        good: Resource that is scarce.
        severity_threshold: Severity level for crisis climax.
        
    Returns:
        Configured StoryArc for the crisis.
    """
    def payoff_condition(ws: Dict[str, Any]) -> bool:
        shortages = ws.get("shortages", {})
        severity = shortages.get(location, {}).get(good, 0.0)
        return severity >= severity_threshold
    
    return StoryArc(
        id=f"crisis_{location}_{good}",
        description=f"{location} faces critical shortage of {good}",
        payoff_condition=payoff_condition,
        payoff_description=f"The {good} crisis in {location} reaches its peak",
        metadata={"location": location, "good": good, "type": "crisis"},
    )


def create_rising_power_arc(faction: str, power_threshold: float = 0.8) -> StoryArc:
    """Create a rising power arc that completes when faction becomes dominant.
    
    Args:
        faction: Faction ID rising to power.
        power_threshold: Power level for arc completion.
        
    Returns:
        Configured StoryArc for rising power.
    """
    def payoff_condition(ws: Dict[str, Any]) -> bool:
        factions = ws.get("factions", {})
        faction_data = factions.get(faction, {})
        return faction_data.get("power", 0.0) >= power_threshold
    
    return StoryArc(
        id=f"rising_power_{faction}",
        description=f"{faction} begins its rise to dominance",
        payoff_condition=payoff_condition,
        payoff_description=f"{faction} has become a dominant power",
        metadata={"faction": faction, "type": "rising_power"},
    )