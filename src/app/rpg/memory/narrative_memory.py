"""Narrative Memory System — TIER 9: Narrative Intelligence Layer.

This module implements the Narrative Memory System from Tier 9 of the RPG design specification.

Purpose:
    Provide token-efficient memory storage that preserves story continuity
    while preventing context explosion. Store important events only.

The Problem:
    - Every world event consumes tokens in narrative context
    - Token limits cause truncation of important story elements
    - No distinction between critical and trivial events
    - Story continuity breaks when events are lost

The Solution:
    NarrativeMemory stores events with importance filtering:
    - Only high-importance events (importance > 0.5) are stored
    - When max capacity reached, events are summarized into compact form
    - Summaries preserve narrative beats without detail explosion
    - Recent events kept raw, older events become summaries

Usage:
    memory = NarrativeMemory(max_entries=100)
    memory.add_events(world_events)
    
    # Get context for narrative generation
    context = memory.get_context()  # Raw events + summaries

Architecture:
    Events → Importance Filter → Event Storage → Summarization (LLM Hook)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class NarrativeMemory:
    """Token-efficient narrative memory with importance filtering and summarization.
    
    The NarrativeMemory system prevents token explosion while preserving
    story continuity. It uses a two-tier approach:
    1. Raw events (recent, important events stored verbatim)
    2. Summaries (older events compressed into narrative summaries)
    
    When raw event count exceeds max_entries, a summarization pass
    compresses older events into summary entries.
    
    Integration Points:
        - PlayerLoop.step(): add_events called each tick
        - Narrative Renderer: get_context for narrative generation
        - LLM Hook: _summarize can be overridden for LLM-powered summaries
    
    Usage:
        memory = NarrativeMemory(max_entries=100)
        
        # Each tick
        memory.add_events(world_events)
        
        # For narrative generation
        context = memory.get_context()
    """
    
    def __init__(self, max_entries: int = 100):
        """Initialize the NarrativeMemory.
        
        Args:
            max_entries: Maximum raw events before summarization triggers.
        """
        self.events: List[Dict[str, Any]] = []
        self.summaries: List[Dict[str, Any]] = []
        self.max_entries = max_entries
    
    def add_events(self, events: List[Dict[str, Any]]) -> None:
        """Add events to memory, filtering by importance.
        
        Only events with importance > 0.5 are stored. After adding,
        checks if summarization is needed.
        
        Args:
            events: List of world event dicts.
        """
        for event in events:
            if event.get("importance", 0.5) > 0.5:
                self.events.append(event)
        
        # Summarize if over capacity
        if len(self.events) > self.max_entries:
            self._summarize()
    
    def add_event(self, event: Dict[str, Any]) -> None:
        """Add a single event to memory.
        
        Args:
            event: World event dict.
        """
        if event.get("importance", 0.5) > 0.5:
            self.events.append(event)
            
            if len(self.events) > self.max_entries:
                self._summarize()
    
    def get_context(self) -> Dict[str, Any]:
        """Get current memory context for narrative generation.
        
        Returns recent raw events plus narrative summaries.
        
        Returns:
            Dict with "recent_events" and "summaries" keys.
        """
        # Return up to 20 most recent raw events
        recent = self.events[-20:] if len(self.events) > 20 else list(self.events)
        
        return {
            "recent_events": recent,
            "summaries": self.summaries[-5:] if len(self.summaries) > 5 else list(self.summaries),
            "total_events_stored": len(self.events),
            "total_summaries": len(self.summaries),
        }
    
    def get_recent_events(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get most recent raw events.
        
        Args:
            count: Number of events to return.
            
        Returns:
            List of recent event dicts.
        """
        return self.events[-count:] if len(self.events) > count else list(self.events)
    
    def get_summaries(self) -> List[Dict[str, Any]]:
        """Get all narrative summaries.
        
        Returns:
            List of summary dicts.
        """
        return list(self.summaries)
    
    def _summarize(self) -> None:
        """Compress older events into a summary entry.
        
        Moves the oldest half of events into a summary and clears them
        from the raw events list. This keeps recent events available
        while compressing older content.
        
        Override this method to use LLM-powered summarization.
        """
        # Take oldest half of events for summarization
        num_to_summarize = len(self.events) // 2
        
        if num_to_summarize == 0:
            return
        
        events_to_summarize = self.events[:num_to_summarize]
        self.events = self.events[num_to_summarize:]
        
        # Create summary entry
        summary = self._create_summary(events_to_summarize)
        self.summaries.append(summary)
    
    def _create_summary(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a summary from a list of events.
        
        Default implementation creates a simple count-based summary.
        Override for LLM-powered summarization.
        
        Args:
            events: Events to summarize.
            
        Returns:
            Summary dict with type and text keys.
        """
        # Count event types
        type_counts: Dict[str, int] = {}
        for event in events:
            event_type = event.get("type", "unknown")
            type_counts[event_type] = type_counts.get(event_type, 0) + 1
        
        # Create summary text
        type_parts = []
        for event_type, count in type_counts.items():
            if count > 1:
                type_parts.append(f"{count} {event_type} events")
            else:
                type_parts.append(f"1 {event_type} event")
        
        summary_text = f"{len(events)} major events occurred: {', '.join(type_parts)}."
        
        return {
            "type": "summary",
            "text": summary_text,
            "event_count": len(events),
            "event_types": type_counts,
        }
    
    def clear(self) -> None:
        """Clear all memory data."""
        self.events.clear()
        self.summaries.clear()
    
    def reset(self) -> None:
        """Reset memory to initial state."""
        self.clear()
    
    def get_memory_size(self) -> int:
        """Get total memory footprint (events + summaries).
        
        Returns:
            Combined count of stored events and summaries.
        """
        return len(self.events) + len(self.summaries)