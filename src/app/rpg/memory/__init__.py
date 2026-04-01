"""Memory Module - Manages NPC memory storage, retrieval, and decay.

Submodules:
- retrieval: Talemate-style memory scoring and retrieval with structured queries
- reflection: Converts memories into high-level beliefs
- consolidation: Merges repeated memories and converts to semantic form

Memory Types:
- episodic: Event-based memories ("what happened")
- semantic: Belief-based memories ("what is true")
- relationship: Relationship state memories ("how I feel about X")
"""

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

__all__ = [
    "compute_recency_decay",
    "compute_relevance",
    "compute_weighted_importance",
    "score_memory",
    "retrieve_memories",
    "retrieve_with_filters",
    "MEMORY_TYPES",
    "RETRIEVAL_WEIGHTS",
    "reflect",
    "store_reflection",
    "reflect_all",
    "consolidate_memories",
    "merge_repeated_events",
    "convert_to_semantic",
]
