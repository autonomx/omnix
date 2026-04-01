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

from rpg.memory.episodic import (
    Episode,
    EpisodeBuilder,
    chunk_events_into_episodes,
    compute_event_importance,
    compute_episode_importance,
)
from rpg.memory.retrieval import (
    compute_recency_decay,
    compute_relevance,
    compute_weighted_importance,
    score_memory,
    retrieve_memories,
    retrieve_with_filters,
    MEMORY_TYPES,
    RETRIEVAL_WEIGHTS,
)
from rpg.memory.reflection import (
    reflect,
    store_reflection,
    reflect_all,
)
from rpg.memory.consolidation import (
    consolidate_memories,
    merge_repeated_events,
    convert_to_semantic,
)
from rpg.memory.belief_system import (
    BeliefSystem,
    compute_belief_influence,
)
from rpg.memory.relationships import (
    get_relationship,
    update_relationship_from_event,
    get_relationship_summary,
    get_all_relationship_summaries,
    get_relationship_goal_override,
)
from rpg.memory.memory_manager import (
    MemoryManager,
    MAX_RAW_EVENTS,
    MAX_EPISODES,
    MAX_MEMORY_IN_PROMPT,
    EPISODE_BUILD_THRESHOLD,
)
from rpg.memory.summarizer import MemorySummarizer

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
]
