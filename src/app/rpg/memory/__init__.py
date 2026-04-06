"""Memory Module - 4-layer memory system with entity indexing.

Submodules:
- episodic: Compressed episode-based memories (Layer 3)
- retrieval: Talemate-style memory scoring and retrieval
- consolidation: Merges repeated memories, converts to semantic
- belief_system: Derived truth layer from memories for GOAP/Story
- relationships: Persistent relationship state between NPCs
- memory_manager: Unified 4-layer memory manager (entry point)

Memory Layers:
- Layer 1: Raw Events (short-term, last N events)
- Layer 2: Narrative Events (compressed summaries)
- Layer 3: Episodic Memory (chunked episodes with TTL)
- Layer 4: Semantic Memory (long-term beliefs/facts)
"""

from app.rpg.memory.episodic import (
    Episode,
    EpisodeBuilder,
    chunk_events_into_episodes,
    compute_event_importance,
    compute_episode_importance,
)
from app.rpg.memory.retrieval import (
    compute_recency_decay,
    compute_relevance,
    compute_weighted_importance,
    score_memory,
    retrieve_memories,
    retrieve_with_filters,
    MEMORY_TYPES,
    RETRIEVAL_WEIGHTS,
)
from app.rpg.memory.reflection import (
    reflect,
    store_reflection,
    reflect_all,
)
from app.rpg.memory.consolidation import (
    consolidate_memories,
    merge_repeated_events,
    convert_to_semantic,
)
from app.rpg.memory.belief_system import (
    BeliefSystem,
    compute_belief_influence,
)
from app.rpg.memory.relationships import (
    get_relationship,
    update_relationship_from_event,
    get_relationship_summary,
    get_all_relationship_summaries,
    get_relationship_goal_override,
)
from app.rpg.memory.memory_manager import (
    MemoryManager,
    MAX_RAW_EVENTS,
    MAX_EPISODES,
    MAX_MEMORY_IN_PROMPT,
    EPISODE_BUILD_THRESHOLD,
)
from app.rpg.memory.summarizer import MemorySummarizer

# Phase 7.7 — Memory / Read-Model Layer
from app.rpg.memory.models import (
    JournalEntry,
    RecapSnapshot,
    CodexEntry,
    CampaignMemorySnapshot,
)
from app.rpg.memory.journal_builder import JournalBuilder
from app.rpg.memory.recap_builder import RecapBuilder as Phase77RecapBuilder
from app.rpg.memory.codex_builder import CodexBuilder
from app.rpg.memory.campaign_memory_builder import CampaignMemoryBuilder
from app.rpg.memory.presenters import MemoryPresenter
from app.rpg.memory.core import CampaignMemoryCore

# Phase 14.0 — Bounded memory lanes (short-term / long-term / world)
from app.rpg.memory.memory_state import (
    append_long_term_memory,
    append_short_term_memory,
    append_world_memory,
    ensure_memory_state,
)


def update_memory(session, events):
    """Update session memory with new events.
    
    This is a compatibility function used by the pipeline.
    It appends events to the session's recent_events list.
    
    Args:
        session: The game session.
        events: List of events to record.
    """
    if not hasattr(session, 'recent_events'):
        session.recent_events = []
    session.recent_events.extend(events or [])
    session.recent_events = session.recent_events[-100:]


__all__ = [
    # Episodic (Layer 3)
    "Episode",
    "EpisodeBuilder",
    "chunk_events_into_episodes",
    "compute_event_importance",
    "compute_episode_importance",
    # Retrieval
    "compute_recency_decay",
    "compute_relevance",
    "compute_weighted_importance",
    "score_memory",
    "retrieve_memories",
    "retrieve_with_filters",
    "MEMORY_TYPES",
    "RETRIEVAL_WEIGHTS",
    # Reflection
    "reflect",
    "store_reflection",
    "reflect_all",
    # Consolidation
    "consolidate_memories",
    "merge_repeated_events",
    "convert_to_semantic",
    # Belief System
    "BeliefSystem",
    "compute_belief_influence",
    # Relationships
    "get_relationship",
    "update_relationship_from_event",
    "get_relationship_summary",
    "get_all_relationship_summaries",
    "get_relationship_goal_override",
    # Memory Manager (main entry point)
    "MemoryManager",
    "MemorySummarizer",
    "MAX_RAW_EVENTS",
    "MAX_EPISODES",
    "MAX_MEMORY_IN_PROMPT",
    "EPISODE_BUILD_THRESHOLD",
    # Phase 7.7 — Memory / Read-Model Layer
    "JournalEntry",
    "RecapSnapshot",
    "CodexEntry",
    "CampaignMemorySnapshot",
    "JournalBuilder",
    "Phase77RecapBuilder",
    "CodexBuilder",
    "CampaignMemoryBuilder",
    "MemoryPresenter",
    "CampaignMemoryCore",
    "update_memory",
    # Phase 14.0
    "append_long_term_memory",
    "append_short_term_memory",
    "append_world_memory",
    "ensure_memory_state",
]
