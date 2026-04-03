"""PHASE 2.5 — SNAPSHOT MANAGER

Provides snapshot-based state serialization for fast replay.

Core capabilities:
- Save game state at periodic intervals
- Load game state from any saved snapshot
- Find nearest snapshot before a target tick
- Enable hybrid replay (snapshot + events) for O(1) state recovery

Without snapshots, replay requires O(n) event processing from tick 0.
With snapshots, replay becomes O(1) state load + O(m) events where m << n.

Usage:
    manager = SnapshotManager()
    
    # In game loop - save periodically
    if tick % 50 == 0:
        manager.save_snapshot(tick, loop)
    
    # For replay - find nearest snapshot and replay events after it
    snapshot_tick = manager.nearest_snapshot(target_tick)
    if snapshot_tick is not None:
        manager.load_snapshot(snapshot_tick, loop)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


class SerializableSystem(Protocol):
    """Protocol for systems that can be serialized/deserialized."""
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize system state to a dictionary.
        
        Returns:
            Dictionary containing all system state data.
        """
        ...
    
    def deserialize(self, data: Dict[str, Any]) -> None:
        """Restore system state from a dictionary.
        
        Args:
            data: Dictionary containing serialized state data.
        """
        ...


class GameLoopLike(Protocol):
    """Protocol for game loop objects that support snapshot operations."""
    
    world: Optional[SerializableSystem]
    npc_system: Optional[SerializableSystem]
    

@dataclass
class Snapshot:
    """A single game state snapshot at a specific tick.
    
    Attributes:
        tick: The game tick number when this snapshot was taken.
        world_state: Serialized world state (may be None if no world system).
        npc_state: Serialized NPC system state (may be None if no NPC system).
        director_state: Serialized story director state.
        timeline_state: Serialized timeline/event bus state.
        effect_state: Serialized effect manager state.
        rng_state: Serialized RNG state.
        planner_state: Serialized NPC planner state.
        extra_states: Additional system states keyed by name.
    """
    tick: int
    world_state: Optional[Dict[str, Any]] = None
    npc_state: Optional[Dict[str, Any]] = None
    director_state: Optional[Dict[str, Any]] = None
    timeline_state: Optional[Dict[str, Any]] = None
    effect_state: Optional[Dict[str, Any]] = None
    rng_state: Optional[Dict[str, Any]] = None
    planner_state: Optional[Dict[str, Any]] = None
    llm_state: Optional[Dict[str, Any]] = None
    extra_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class SnapshotManager:
    """Manages game state snapshots for fast replay and save/load.
    
    This system enables O(1) state recovery by storing periodic snapshots
    of the game state. Instead of replaying all events from tick 0, the
    replay engine can:
    
    1. Find the nearest snapshot before the target tick
    2. Load that snapshot to get the state at that point
    3. Replay only the events after the snapshot tick
    
    This transforms replay from O(n) to O(1) + O(m) where m << n.
    
    Attributes:
        _snapshots: Dictionary mapping tick number to Snapshot objects.
        _snapshot_interval: How often to save snapshots (default 50 ticks).
    """
    
    def __init__(self, snapshot_interval: int = 50):
        """Initialize the SnapshotManager.
        
        Args:
            snapshot_interval: Number of ticks between automatic snapshots.
                              Default is 50 ticks.
        """
        self._snapshots: Dict[int, Snapshot] = {}
        self._snapshot_interval = snapshot_interval
    
    def save_snapshot(self, tick: int, loop: Any) -> None:
        """Save a snapshot of the current game state.
        
        Serializes all available systems into a Snapshot object and stores
        it indexed by tick number.
        
        Args:
            tick: The current game tick (used as snapshot key).
            loop: The game loop object to serialize. Must have serializable
                 systems like 'world', 'npc_system', etc.
        """
        snapshot = Snapshot(tick=tick)
        
        # Serialize world state if available
        if hasattr(loop, "world"):
            if hasattr(loop.world, "serialize_state"):
                snapshot.world_state = loop.world.serialize_state()
            elif hasattr(loop.world, "serialize"):
                snapshot.world_state = loop.world.serialize()
        
        # Serialize NPC system state if available
        if hasattr(loop, "npc_system"):
            if hasattr(loop.npc_system, "serialize_state"):
                snapshot.npc_state = loop.npc_system.serialize_state()
            elif hasattr(loop.npc_system, "serialize"):
                snapshot.npc_state = loop.npc_system.serialize()
        
        # PHASE 5.5: Serialize additional state
        if hasattr(loop, "story_director") and hasattr(loop.story_director, "serialize_state"):
            snapshot.director_state = loop.story_director.serialize_state()
        
        if hasattr(loop, "event_bus") and hasattr(loop.event_bus, "timeline"):
            timeline = loop.event_bus.timeline
            if hasattr(timeline, "serialize_state"):
                snapshot.timeline_state = {
                    "timeline": timeline.serialize_state(),
                    "seen_event_ids": list(getattr(loop.event_bus, "_seen_event_ids", [])),
                    "seq": getattr(loop.event_bus, "_seq", 0),
                    "current_tick": getattr(loop.event_bus, "_current_tick", None),
                }
        
        if hasattr(loop, "effect_manager") and hasattr(loop.effect_manager, "serialize_state"):
            snapshot.effect_state = loop.effect_manager.serialize_state()
        
        if hasattr(loop, "rng") and hasattr(loop.rng, "getstate"):
            snapshot.rng_state = {"state": loop.rng.getstate()}
        
        if hasattr(loop, "npc_planner") and loop.npc_planner is not None:
            if hasattr(loop.npc_planner, "serialize_state"):
                snapshot.planner_state = loop.npc_planner.serialize_state()
        
        # PHASE 5.6: Serialize LLM recorder state
        if hasattr(loop, "llm_recorder") and loop.llm_recorder is not None:
            if hasattr(loop.llm_recorder, "serialize_state"):
                snapshot.llm_state = loop.llm_recorder.serialize_state()
        
        # Serialize any additional systems that declare serialize()
        # This allows extensions to opt into snapshot support
        for attr_name in getattr(loop, "_snapshot_systems", []):
            system = getattr(loop, attr_name, None)
            if system is not None and hasattr(system, "serialize"):
                snapshot.extra_states[attr_name] = system.serialize()
        
        self._snapshots[tick] = snapshot
    
    def load_snapshot(self, tick: int, loop: Any) -> bool:
        """Load a snapshot and restore game state.
        
        Restores all serialized system states from the snapshot into
        the provided game loop object.
        
        Args:
            tick: The tick number of the snapshot to load.
            loop: The game loop object to restore state into.
            
        Returns:
            True if snapshot was found and loaded, False otherwise.
        """
        snapshot = self._snapshots.get(tick)
        if snapshot is None:
            return False
        
        # Restore world state if available
        if snapshot.world_state and hasattr(loop, "world"):
            if hasattr(loop.world, "deserialize_state"):
                loop.world.deserialize_state(snapshot.world_state)
            elif hasattr(loop.world, "deserialize"):
                loop.world.deserialize(snapshot.world_state)
        
        # Restore NPC system state if available
        if snapshot.npc_state and hasattr(loop, "npc_system"):
            if hasattr(loop.npc_system, "deserialize_state"):
                loop.npc_system.deserialize_state(snapshot.npc_state)
            elif hasattr(loop.npc_system, "deserialize"):
                loop.npc_system.deserialize(snapshot.npc_state)
        
        # PHASE 5.5: Restore additional state
        if snapshot.director_state and hasattr(loop, "story_director"):
            if hasattr(loop.story_director, "deserialize_state"):
                loop.story_director.deserialize_state(snapshot.director_state)

        if snapshot.timeline_state and hasattr(loop, "event_bus") and hasattr(loop.event_bus, "timeline"):
            timeline = loop.event_bus.timeline
            if hasattr(timeline, "deserialize_state"):
                ts = snapshot.timeline_state
                if isinstance(ts, dict) and "timeline" in ts:
                    timeline.deserialize_state(ts.get("timeline", {}))
                else:
                    timeline.deserialize_state(ts)
            if hasattr(loop.event_bus, "_seen_event_ids"):
                from collections import deque
                maxlen = getattr(loop.event_bus._seen_event_ids, "maxlen", 100000)
                restored_seen = snapshot.timeline_state.get("seen_event_ids", [])
                loop.event_bus._seen_event_ids = deque(restored_seen, maxlen=maxlen)
                loop.event_bus._seen_event_ids_set = set(restored_seen)
            if hasattr(loop.event_bus, "_seq"):
                loop.event_bus._seq = snapshot.timeline_state.get("seq", 0)
            if hasattr(loop.event_bus, "_current_tick"):
                loop.event_bus._current_tick = snapshot.timeline_state.get("current_tick", None)

        if snapshot.rng_state and hasattr(loop, "rng") and hasattr(loop.rng, "setstate"):
            loop.rng.setstate(snapshot.rng_state["state"])
        elif snapshot.rng_state and hasattr(loop, "rng") and hasattr(loop.rng, "deserialize_state"):
            loop.rng.deserialize_state(snapshot.rng_state)

        if snapshot.effect_state and hasattr(loop, "effect_manager"):
            if hasattr(loop.effect_manager, "deserialize_state"):
                loop.effect_manager.deserialize_state(snapshot.effect_state)
        
        if snapshot.planner_state and hasattr(loop, "npc_planner") and loop.npc_planner is not None:
            if hasattr(loop.npc_planner, "deserialize_state"):
                loop.npc_planner.deserialize_state(snapshot.planner_state)

        if snapshot.llm_state and hasattr(loop, "llm_recorder") and loop.llm_recorder is not None:
            if hasattr(loop.llm_recorder, "deserialize_state"):
                loop.llm_recorder.deserialize_state(snapshot.llm_state)
        
        # Restore any additional system states
        for attr_name, state_data in snapshot.extra_states.items():
            system = getattr(loop, attr_name, None)
            if system is not None and hasattr(system, "deserialize"):
                system.deserialize(state_data)
        
        return True
    
    def nearest_snapshot(self, tick: int) -> Optional[int]:
        """Find the tick number of the nearest snapshot at or before the given tick.
        
        This is useful for hybrid replay: find the closest checkpoint,
        load it, then replay events from that point.
        
        Args:
            tick: The target tick to find a snapshot for.
            
        Returns:
            The tick number of the nearest snapshot <= target tick,
            or None if no such snapshot exists.
        """
        candidates = [t for t in self._snapshots if t <= tick]
        return max(candidates) if candidates else None
    
    def has_snapshot(self, tick: int) -> bool:
        """Check if a snapshot exists for the given tick.
        
        Args:
            tick: The tick number to check.
            
        Returns:
            True if a snapshot exists for the given tick.
        """
        return tick in self._snapshots
    
    def remove_snapshot(self, tick: int) -> bool:
        """Remove a snapshot at the given tick.
        
        Args:
            tick: The tick number of the snapshot to remove.
            
        Returns:
            True if snapshot was removed, False if it didn't exist.
        """
        if tick in self._snapshots:
            del self._snapshots[tick]
            return True
        return False
    
    def clear(self) -> None:
        """Remove all snapshots and free memory."""
        self._snapshots.clear()
    
    def snapshot_count(self) -> int:
        """Return the number of snapshots currently stored."""
        return len(self._snapshots)
    
    def snapshot_ticks(self) -> List[int]:
        """Return a sorted list of all snapshot tick numbers."""
        return sorted(self._snapshots.keys())
    
    def should_snapshot(self, tick: int) -> bool:
        """Check if the current tick matches the snapshot interval.
        
        This is used by the game loop to know when to save a snapshot.
        
        Args:
            tick: The current game tick.
            
        Returns:
            True if a snapshot should be saved at this tick.
        """
        return tick > 0 and tick % self._snapshot_interval == 0