"""Memory Manager v2 — Cognitive layer with types, decay, and contradiction detection.

STEP 2 — Memory System → Cognitive Layer: Upgraded from flat memory to
decision-grade memory with semantic types, exponential decay, goal-aware
retrieval boost, and contradiction detection.

The Problem: Flat memories don't differentiate between event types,
don't decay over time, and can lead to inconsistent NPC beliefs.

The Solution: Structured memory types with exponential decay, goal-aware
retrieval boosting, and contradiction resolution.

Architecture:
    Events → [episodic|semantic|emotional|goal_related] → Decayed → Retrieved

Usage:
    manager = MemoryManager(session)
    manager.add_event(event, memory_type="episodic")
    memories = manager.retrieve(query_entities=["player"], current_goal="hunt")

Key Features:
    - Memory types: episodic, semantic, emotional, goal_related
    - Exponential decay: older memories fade naturally
    - Goal-aware retrieval boost: goal-related memories surface easier
    - Contradiction detection: prevents conflicting beliefs
    - Emotional memory amplification: emotional events remembered more
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.rpg.memory.belief_system import BeliefSystem
from app.rpg.memory.episodic import (
    Episode,
    EpisodeBuilder,
    compute_event_importance,
)
from app.rpg.memory.retrieval import (
    compute_recency_decay,
)

# Configuration
MAX_RAW_EVENTS = 50
MAX_NARRATIVE_EVENTS = 30
MAX_EPISODES = 50
MAX_SEMANTIC_BELIEFS = 100
MAX_MEMORY_IN_PROMPT = 5
EPISODE_BUILD_THRESHOLD = 10

# STEP 2: Memory types
MEMORY_TYPES = {"episodic", "semantic", "emotional", "goal_related"}

# Goal-aware retrieval boost
GOAL_BOOST = 0.3

# Emotional memory amplification
EMOTIONAL_AMPLIFIER = 1.5

# Decay half-life (ticks)
DECAY_HALF_LIFE = 50

# [FIX #2] Belief confidence tracking
CONFIDENCE_DECAY = 0.8
CONFIDENCE_INCREMENT = 0.2
MIN_CONFIDENCE = 0.1
MAX_CONFIDENCE = 1.0
CONFIDENCE_FLIP_THRESHOLD = 0.3  # Min confidence to allow belief flips


class MemoryManager:
    """Cognitive memory manager with types, decay, and contradiction detection."""

    def __init__(
        self,
        session=None,
        max_raw_events: int = MAX_RAW_EVENTS,
        max_episodes: int = MAX_EPISODES,
        episode_build_threshold: int = EPISODE_BUILD_THRESHOLD,
    ):
        self.session = session
        # Layer 1
        self.raw_events: List[Dict[str, Any]] = []
        self._max_raw = max_raw_events
        # Layer 2
        self.narrative_events: List[Dict[str, Any]] = []
        # Layer 3
        self.episodes: List[Episode] = []
        self._max_episodes = max_episodes
        # Layer 4
        self.semantic_beliefs: List[Dict[str, Any]] = []
        # Entity index
        self.entity_index: Dict[str, List[Episode]] = defaultdict(list)
        # Builder state
        self._pending_events: List[Dict[str, Any]] = []
        self._episode_threshold = episode_build_threshold
        # Beliefs
        self.belief_system = BeliefSystem()

    def add_event(
        self,
        event: Dict[str, Any],
        current_tick: int = 0,
        memory_type: str = "episodic",
        goal_tags: Optional[List[str]] = None,
    ) -> None:
        """Add an event to the memory system, flowing through all layers.
        
        Args:
            event: Event dict.
            current_tick: Current game tick.
            memory_type: One of MEMORY_TYPES.
            goal_tags: Tags related to current NPC goals for boosting.
        """
        if current_tick == 0:
            current_tick = self._get_current_tick()
        if "timestamp" not in event:
            event["timestamp"] = current_tick
        if "tick" not in event:
            event["tick"] = current_tick
            
        # STEP 2: Tag with memory type
        event["memory_type"] = memory_type if memory_type in MEMORY_TYPES else "episodic"
        
        # Goal tags for retrieval boost
        if goal_tags:
            event["goal_tags"] = goal_tags
            
        self._add_raw_event(event)
        self._add_narrative_event(event)
        self._pending_events.append(event)
        if len(self._pending_events) >= self._episode_threshold:
            self.build_episode()
        self._update_beliefs_from_event(event)

    def add_events(
        self, events: List[Dict[str, Any]], current_tick: int = 0
    ) -> int:
        """Add multiple events at once. Returns episodes built count."""
        count = 0
        for event in events:
            before = len(self._pending_events)
            self.add_event(event, current_tick=current_tick)
            if len(self._pending_events) < before:
                count += 1
        return count

    def _add_raw_event(self, event: Dict[str, Any]) -> None:
        self.raw_events.append(event)
        if len(self.raw_events) > self._max_raw:
            self.raw_events = self.raw_events[-self._max_raw:]

    def _add_narrative_event(self, event: Dict[str, Any]) -> None:
        if event.get("type") == "narrative_event":
            narrative = event
        elif "summary" in event:
            narrative = event.copy()
        else:
            narrative = self._create_narrative_from_event(event)
        if "importance" not in narrative:
            narrative["importance"] = compute_event_importance(event)
        entities = self._extract_entities(event)
        narrative["entities"] = list(entities)
        # STEP 2: Pass through memory type
        narrative["memory_type"] = event.get("memory_type", "episodic")
        self.narrative_events.append(narrative)
        if len(self.narrative_events) > MAX_NARRATIVE_EVENTS:
            self.narrative_events = self.narrative_events[-MAX_NARRATIVE_EVENTS:]

    def _create_narrative_from_event(
        self, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        event_type = event.get("type", "event")
        source = event.get("source", event.get("actor", "unknown"))
        target = event.get("target", "unknown")
        return {
            "type": "narrative_event",
            "original_type": event_type,
            "summary": f"{source} {event_type} {target}",
            "tags": [event_type],
            "source": source,
            "target": target,
            "timestamp": event.get("timestamp", event.get("tick", 0)),
            "memory_type": event.get("memory_type", "episodic"),
        }

    @staticmethod
    def _extract_entities(event: Dict[str, Any]) -> set:
        entities = set()
        for key in ("source", "target", "actor", "npc_id"):
            val = event.get(key)
            if val and isinstance(val, str):
                entities.add(val)
        for e in event.get("entities", []):
            if e:
                entities.add(e)
        return entities

    def build_episode(self) -> Optional[Episode]:
        """Build an episode from pending events."""
        if not self._pending_events:
            return None
        current_tick = self._get_current_tick()
        episode = EpisodeBuilder.from_events(
            self._pending_events, current_tick=current_tick
        )
        self.episodes.append(episode)
        for entity_id in episode.entities:
            self.entity_index[entity_id].append(episode)
        self._prune_episodes()
        self._pending_events.clear()
        return episode

    def force_build_episode(
        self, events: List[Dict[str, Any]]
    ) -> Episode:
        current_tick = self._get_current_tick()
        episode = EpisodeBuilder.from_events(
            events, current_tick=current_tick
        )
        self.episodes.append(episode)
        for entity_id in episode.entities:
            self.entity_index[entity_id].append(episode)
        self._prune_episodes()
        return episode

    # ---------------------------------------------------------------
    # STEP 2: Exponential memory decay
    # ---------------------------------------------------------------

    def apply_decay(self, episode: Episode, current_tick: int) -> None:
        """Apply exponential decay to an episode's importance.
        
        Decay formula: score *= exp(-age / half_life)
        
        Args:
            episode: Episode to decay.
            current_tick: Current game tick.
        """
        age = current_tick - episode.tick_created
        decay = math.exp(-age / DECAY_HALF_LIFE)
        episode.importance *= decay
        episode.importance = max(episode.importance, 0.01)

    def _prune_episodes(self) -> None:
        current_tick = self._get_current_tick()
        # Apply decay to all episodes
        for ep in self.episodes:
            self.apply_decay(ep, current_tick)
        self.episodes = [
            ep for ep in self.episodes if not ep.is_expired(current_tick)
        ]
        if len(self.episodes) > self._max_episodes:
            self.episodes.sort(key=lambda e: e.importance, reverse=True)
            self.episodes = self.episodes[: self._max_episodes]
        self._rebuild_entity_index()

    def _rebuild_entity_index(self) -> None:
        self.entity_index.clear()
        for episode in self.episodes:
            for entity_id in episode.entities:
                self.entity_index[entity_id].append(episode)

    def _update_beliefs_from_event(self, event: Dict[str, Any]) -> None:
        importance = compute_event_importance(event)
        if importance < 0.6:
            return
        belief = self._extract_belief(event)
        if belief:
            self._add_or_update_belief(belief)

    def _extract_belief(
        self, event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        event_type = event.get("type", "")
        source = event.get("source", event.get("actor", ""))
        target = event.get("target", "")
        if not (source and target):
            return None
        belief_map = {
            "damage": {
                "value": -0.3,
                "reason": f"{source} harmed {target}",
                "importance": 0.7,
            },
            "death": {
                "value": -0.8,
                "reason": f"{source} killed {target}",
                "importance": 1.0,
            },
            "heal": {
                "value": 0.4,
                "reason": f"{source} healed {target}",
                "importance": 0.5,
            },
            "betrayal": {
                "value": -1.0,
                "reason": f"{source} betrayed {target}",
                "importance": 1.0,
            },
            "alliance_formed": {
                "value": 0.6,
                "reason": f"{source} allied with {target}",
                "importance": 0.7,
            },
        }
        if event_type in belief_map:
            b = belief_map[event_type]
            return {
                "type": "relationship",
                "entity": target,
                "target_entity": source,
                "value": b["value"],
                "reason": b["reason"],
                "importance": b["importance"],
            }
        if event_type == "story_event":
            return {
                "type": "fact",
                "entity": source or target,
                "fact": event.get("summary", event.get("text", "")),
                "importance": 0.8,
            }
        return None

    # ---------------------------------------------------------------
    # STEP 2: Contradiction detection
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
    # [FIX #2] Belief confidence tracking
    # ---------------------------------------------------------------

    def _resolve_contradiction(
        self, belief: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Check for contradictory beliefs and resolve them with confidence.
        
        [FIX #2] Uses confidence to prevent belief flip-flopping:
        - If existing belief has high confidence, new belief is suppressed
        - If existing belief has low confidence, it can be updated
        
        Contradiction = opposing values (one positive, one negative)
        for the same entity relationship.
        """
        entity = belief.get("entity", "")
        target = belief.get("target_entity", "")
        new_val = belief.get("value", 0)
        
        for existing in self.semantic_beliefs:
            if (
                existing.get("entity") == entity
                and existing.get("target_entity") == target
            ):
                old_val = existing.get("value", 0)
                # Check for contradiction (opposite signs)
                if (old_val > 0.2 and new_val <= -0.2) or (
                    old_val < -0.2 and new_val >= 0.2
                ):
                    # [FIX #2] Confidence-based resolution
                    old_conf = existing.get("confidence", 0.5)
                    if old_conf < CONFIDENCE_FLIP_THRESHOLD:
                        # Low confidence - allow belief update
                        existing["value"] = new_val
                        existing["reason"] = belief.get(
                            "reason", existing.get("reason", "")
                        )
                        existing["importance"] = max(
                            existing.get("importance", 0),
                            belief.get("importance", 0),
                        )
                        existing["confidence"] = CONFIDENCE_INCREMENT
                        return None
                    else:
                        # High confidence - suppress new belief, decay old slightly
                        existing["confidence"] = max(
                            old_conf * CONFIDENCE_DECAY, MIN_CONFIDENCE
                        )
                        return None
        return belief

    def _add_or_update_belief(self, belief: Dict[str, Any]) -> None:
        belief_type = belief.get("type", "")
        entity = belief.get("entity", "")
        target = belief.get("target_entity", "")
        
        for existing in self.semantic_beliefs:
            if (
                existing.get("type") == belief_type
                and existing.get("entity") == entity
                and existing.get("target_entity") == target
            ):
                old_val = existing.get("value", 0)
                new_val = belief.get("value", 0)
                # Weighted update with [FIX #2] confidence
                old_conf = existing.get("confidence", 0.5)
                weight = CONFIDENCE_INCREMENT  # New evidence weight
                existing["value"] = old_val * (1 - weight) + new_val * weight
                existing["reason"] = belief.get(
                    "reason", existing.get("reason", "")
                )
                existing["importance"] = max(
                    existing.get("importance", 0),
                    belief.get("importance", 0),
                )
                # [FIX #2] Update confidence: decay old + increment new
                existing["confidence"] = min(
                    old_conf * CONFIDENCE_DECAY + CONFIDENCE_INCREMENT,
                    MAX_CONFIDENCE,
                )
                return
                
        # New belief - initialize with default confidence
        if "confidence" not in belief:
            belief["confidence"] = CONFIDENCE_INCREMENT
            
        # Check for contradictions before adding new belief
        resolved = self._resolve_contradiction(belief)
        if resolved is not None:
            self.semantic_beliefs.append(resolved)
        if len(self.semantic_beliefs) > MAX_SEMANTIC_BELIEFS:
            self._prune_beliefs()

    def _prune_beliefs(self) -> None:
        self.semantic_beliefs.sort(
            key=lambda b: b.get("importance", 0), reverse=True
        )
        self.semantic_beliefs = self.semantic_beliefs[:MAX_SEMANTIC_BELIEFS]

    # ---------------------------------------------------------------
    # STEP 2: Retrieval with type boosts and decay
    # ---------------------------------------------------------------

    def retrieve(
        self,
        query_entities: Optional[List[str]] = None,
        query_types: Optional[List[str]] = None,
        limit: int = MAX_MEMORY_IN_PROMPT,
        mode: str = "general",
        current_goal: Optional[str] = None,
        goal_tags: Optional[List[str]] = None,
    ) -> List[Tuple[float, Any]]:
        """Retrieve most relevant memories with cognitive enhancements.
        
        STEP 2 additions:
        - Memory type filtering
        - Goal-aware retrieval boost (+0.3)
        - Exponential decay scoring
        - Emotional amplification (×1.5)
        
        Args:
            query_entities: Entities to match.
            query_types: Memory types to filter.
            limit: Max results.
            mode: Retrieval mode.
            current_goal: Current NPC goal for boosting.
            goal_tags: Tags for goal relevance matching.
        """
        candidates: List[Tuple[float, Any]] = []
        query_set = set(query_entities or [])
        current_tick = self._get_current_tick()

        # Layer 3 - Episodes
        for episode in self.episodes:
            if query_set and not episode.has_any_entity(query_set):
                continue
            score = episode.importance * 0.6
            if query_set:
                overlap = len(episode.entities & query_set)
                score += overlap * 0.1
            
            # Exponential decay
            recency = compute_recency_decay(
                episode.tick_created, current_tick, half_life=DECAY_HALF_LIFE
            )
            score += recency * 0.2
            
            # Goal-aware boost
            if current_goal and episode.tags:
                if current_goal.lower() in " ".join(episode.tags).lower():
                    score += GOAL_BOOST
                    
            # Emotional amplification
            if episode.tags and any(
                t in episode.tags for t in ("death", "betrayal", "combat", "damage")
            ):
                score *= EMOTIONAL_AMPLIFIER
                
            if query_types and not any(
                t in episode.tags for t in query_types
            ):
                continue
            candidates.append((score, episode))

        # Layer 4 - Semantic beliefs
        for belief in self.semantic_beliefs:
            be = belief.get("entity", "")
            te = belief.get("target_entity", "")
            if query_set and be not in query_set and te not in query_set:
                continue
            score = belief.get("importance", 0.5) * 0.7
            score += abs(belief.get("value", 0)) * 0.2
            
            # Goal-aware boost for beliefs
            if current_goal and belief.get("type") == "relationship":
                # Relationships related to current goal are boosted
                if be.lower() == current_goal.lower() or te.lower() == current_goal.lower():
                    score += GOAL_BOOST
                    
            candidates.append((score, belief))

        # Layer 2 - Narrative events
        for narrative in self.narrative_events[-20:]:
            ents = set(narrative.get("entities", []))
            for key in ("source", "target"):
                val = narrative.get(key, "")
                if val:
                    ents.add(val)
            if query_set and not ents.intersection(query_set):
                continue
            relevance = 0.3
            if query_set:
                total = max(len(ents), 1)
                relevance = len(ents & query_set) / total
            recency = compute_recency_decay(
                narrative.get("timestamp", narrative.get("tick", 0)),
                current_tick,
                half_life=30,
            )
            importance = narrative.get("importance", 0.5)
            score = relevance * 0.4 + importance * 0.4 + recency * 0.2
            
            # Emotional amplification
            mem_type = narrative.get("memory_type", "")
            if mem_type == "emotional":
                score *= EMOTIONAL_AMPLIFIER
                
            candidates.append((score, narrative))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[:limit]

    def retrieve_for_entity(
        self, entity_id: str, limit: int = MAX_MEMORY_IN_PROMPT
    ) -> List[Tuple[float, Any]]:
        return self.retrieve(query_entities=[entity_id], limit=limit)

    def retrieve_for_relationship(
        self,
        entity_a: str,
        entity_b: str,
        limit: int = 3,
    ) -> List[Tuple[float, Any]]:
        return self.retrieve(
            query_entities=[entity_a, entity_b], limit=limit
        )

    def get_context_for(
        self,
        query_entities: List[str],
        max_items: int = MAX_MEMORY_IN_PROMPT,
        format_type: str = "narrative",
    ) -> str:
        """Get formatted memory context for LLM prompts."""
        memories = self.retrieve(
            query_entities=query_entities, limit=max_items
        )
        if not memories:
            return "(No relevant memories)"
        if format_type == "structured":
            return self._format_structured(memories)
        return self._format_narrative(memories)

    def _format_narrative(self, memories: List[Tuple[float, Any]]) -> str:
        lines = []
        for _, item in memories:
            if isinstance(item, Episode):
                lines.append(item.summary)
            elif isinstance(item, dict):
                if item.get("type") == "narrative_event":
                    lines.append(item.get("summary", str(item)))
                elif item.get("type") == "relationship":
                    entity = item.get("entity", "?")
                    target = item.get("target_entity", "?")
                    value = item.get("value", 0)
                    reason = item.get("reason", "")
                    sentiment = "positive" if value > 0 else "negative"
                    lines.append(
                        f"{entity} has {sentiment} feelings toward "
                        f"{target}: {reason}"
                    )
                elif item.get("type") == "fact":
                    lines.append(item.get("fact", str(item)))
                else:
                    lines.append(str(item))
            else:
                lines.append(str(item))
        return " | ".join(lines)

    def _format_structured(self, memories: List[Tuple[float, Any]]) -> str:
        lines = ["## Relevant Memories"]
        for score, item in memories:
            if isinstance(item, Episode):
                lines.append(f"- [{score:.2f}] Episode: {item.summary}")
                if item.tags:
                    lines.append(
                        f"  Tags: {', '.join(item.tags[:3])}"
                    )
            elif isinstance(item, dict):
                if item.get("type") == "narrative_event":
                    lines.append(
                        f"- [{score:.2f}] {item.get('summary', '?')}"
                    )
                elif item.get("type") == "relationship":
                    reason = item.get("reason", "")
                    value = item.get("value", 0)
                    lines.append(
                        f"- [{score:.2f}] Relationship: {reason} "
                        f"(val={value:.2f})"
                    )
                elif item.get("type") == "fact":
                    lines.append(
                        f"- [{score:.2f}] Fact: {item.get('fact', '?')}"
                    )
                else:
                    lines.append(f"- [{score:.2f}] {item}")
            else:
                lines.append(f"- [{score:.2f}] {item}")
        return "\n".join(lines)

    def consolidate(self, current_tick: int = 0) -> Dict[str, int]:
        """Run full memory consolidation cycle."""
        if current_tick == 0:
            current_tick = self._get_current_tick()
        stats: Dict[str, int] = {
            "episodes_built": 0,
            "episodes_pruned": 0,
            "beliefs_updated": 0,
        }
        if self._pending_events:
            episode = self.build_episode()
            if episode:
                stats["episodes_built"] = 1
        before = len(self.episodes)
        self._prune_episodes()
        stats["episodes_pruned"] = before - len(self.episodes)
        stats["beliefs_updated"] = self._analyze_patterns_for_beliefs()
        return stats

    def _analyze_patterns_for_beliefs(self) -> int:
        beliefs_created = 0
        hostility: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for episode in self.episodes[-20:]:
            tags = set(episode.tags)
            entities = episode.entities
            if tags & {"damage", "death", "betrayal", "combat"}:
                for entity in entities:
                    for other in entities:
                        if entity != other:
                            hostility[entity][other] += 1
        for source, targets in hostility.items():
            for target, count in targets.items():
                if count >= 3:
                    belief = {
                        "type": "relationship",
                        "entity": source,
                        "target_entity": target,
                        "value": -0.5 - (count * 0.1),
                        "reason": (
                            f"Repeated conflicts with {target} "
                            f"({count} incidents)"
                        ),
                        "importance": min(0.5 + count * 0.1, 1.0),
                    }
                    existing = [
                        b
                        for b in self.semantic_beliefs
                        if (
                            b.get("type") == "relationship"
                            and b.get("entity") == source
                            and b.get("target_entity") == target
                        )
                    ]
                    if not existing:
                        self._add_or_update_belief(belief)
                        beliefs_created += 1
        return beliefs_created

    def _get_current_tick(self) -> int:
        if self.session:
            world = getattr(self.session, "world", None)
            if world:
                return getattr(world, "time", 0)
        return 0

    def reset(self) -> None:
        self.raw_events.clear()
        self.narrative_events.clear()
        self.episodes.clear()
        self.semantic_beliefs.clear()
        self._pending_events.clear()
        self.entity_index.clear()

    def get_stats(self) -> Dict[str, int]:
        return {
            "raw_events": len(self.raw_events),
            "narrative_events": len(self.narrative_events),
            "episodes": len(self.episodes),
            "semantic_beliefs": len(self.semantic_beliefs),
            "pending_events": len(self._pending_events),
            "indexed_entities": len(self.entity_index),
        }
