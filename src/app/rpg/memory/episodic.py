"""Episodic Memory System - Compressed narrative episodes.

This is Layer 3 of the 4-layer memory system.

Episodes are compressed summaries of event sequences that:
- Group related events into coherent narrative units
- Carry importance scores for retrieval priority
- Track all entities involved for indexed retrieval
- Persist beyond raw event windows

Architecture:
    Raw Events -> Narrative Events -> Episodes -> Semantic

Each Episode represents a meaningful "story beat."

Usage:
    episode = EpisodeBuilder.build(events)
    session.memory.episodes.append(episode)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class Episode:
    """A compressed episodic memory summarizing a sequence of events.

    Attributes:
        id: Unique identifier for this episode
        summary: 1-2 sentence narrative description
        key_events: Source events that formed this episode
        entities: All entity IDs involved
        importance: Float 0.0-1.0 indicating significance
        tags: Categorical tags for filtering
        tick_created: World time when episode was created
        ttl: Time-to-live in ticks; 0 = permanent
    """

    summary: str
    key_events: List[Dict[str, Any]] = field(default_factory=list)
    entities: Set[str] = field(default_factory=set)
    importance: float = 0.5
    tags: List[str] = field(default_factory=list)
    id: str = ""
    tick_created: int = 0
    ttl: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = f"ep_{id(self)}_{hash(self.summary) % 10000}"
        if not isinstance(self.entities, set):
            self.entities = set(self.entities)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "key_events": self.key_events[:3],
            "entities": list(self.entities),
            "importance": self.importance,
            "tags": self.tags,
            "tick_created": self.tick_created,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Episode":
        return cls(
            id=data.get("id", ""),
            summary=data.get("summary", ""),
            key_events=data.get("key_events", []),
            entities=set(data.get("entities", [])),
            importance=data.get("importance", 0.5),
            tags=data.get("tags", []),
            tick_created=data.get("tick_created", 0),
            ttl=data.get("ttl", 0),
        )

    def is_expired(self, current_tick: int) -> bool:
        if self.ttl <= 0:
            return False
        return (current_tick - self.tick_created) >= self.ttl

    def has_entity(self, entity_id: str) -> bool:
        return entity_id in self.entities

    def has_any_entity(self, entity_ids: Set[str]) -> bool:
        return bool(self.entities & entity_ids)


_EVENT_IMPORTANCE = {
    "death": 1.0,
    "betrayal": 0.95,
    "critical_hit": 0.85,
    "alliance_formed": 0.7,
    "assist": 0.6,
    "damage": 0.5,
    "heal": 0.5,
    "move": 0.1,
    "dialogue": 0.3,
    "story_event": 0.7,
    "npc_action": 0.2,
}


def compute_event_importance(event: Dict[str, Any]) -> float:
    """Compute importance score for a single event [0.0, 1.0]."""
    event_type = event.get("type", "")
    score = _EVENT_IMPORTANCE.get(event_type, 0.1)
    entities_in_event = _extract_entities_from_event(event)
    if "player" in entities_in_event:
        score += 0.3
    if event_type in ("damage", "death", "betrayal"):
        score += 0.2
    if event.get("memory_type") == "narrative_event":
        summary = event.get("summary", "")
        keywords = ["kill", "die", "death", "betray", "destroy"]
        if any(w in summary.lower() for w in keywords):
            score += 0.3
    emotional = event.get("emotional_intensity", 0)
    score += emotional * 0.2
    return min(score, 1.0)


def compute_episode_importance(events: List[Dict[str, Any]]) -> float:
    """Compute combined importance for a group of events."""
    if not events:
        return 0.0
    importances = [compute_event_importance(e) for e in events]
    max_imp = max(importances)
    significant_count = sum(1 for i in importances if i >= 0.5)
    accumulation_bonus = min(significant_count * 0.1, 0.3)
    return min(max_imp + accumulation_bonus, 1.0)


def _extract_entities_from_event(event: Dict[str, Any]) -> Set[str]:
    entities = set()
    for key in ("source", "target", "actor", "npc_id"):
        val = event.get(key)
        if val and isinstance(val, str):
            entities.add(val)
    for e in event.get("entities", []):
        if e:
            entities.add(e)
    return entities


class EpisodeBuilder:
    """Builds Episode instances from raw/narrative events."""

    def __init__(self):
        self._events: List[Dict[str, Any]] = []
        self._entities: Set[str] = set()
        self._tags: Set[str] = set()

    def add(self, event: Dict[str, Any]) -> None:
        self._events.append(event)
        self._entities.update(_extract_entities_from_event(event))
        for tag in event.get("tags", []):
            self._tags.add(tag)
        event_type = event.get("type", "")
        if event_type:
            self._tags.add(event_type)

    @property
    def event_count(self) -> int:
        return len(self._events)

    def build(self, current_tick: int = 0) -> Episode:
        if not self._events:
            return Episode(
                summary="Nothing significant happened.",
                importance=0.0,
                tick_created=current_tick,
            )
        importance = compute_episode_importance(self._events)
        summary = _generate_episode_summary(self._events)
        ttl = _compute_ttl(importance)
        key_events = _select_key_events(self._events, max_events=5)
        return Episode(
            summary=summary,
            key_events=key_events,
            entities=self._entities.copy(),
            importance=importance,
            tags=sorted(self._tags),
            tick_created=current_tick,
            ttl=ttl,
        )

    @classmethod
    def from_events(
        cls, events: List[Dict[str, Any]], current_tick: int = 0
    ) -> Episode:
        """Convenience factory: build episode from events list."""
        builder = cls()
        for event in events:
            builder.add(event)
        return builder.build(current_tick=current_tick)


def _generate_episode_summary(events: List[Dict[str, Any]]) -> str:
    if not events:
        return "Nothing happened."
    scored = [(compute_event_importance(e), e) for e in events]
    scored.sort(key=lambda x: x[0], reverse=True)
    top_events = scored[:3]
    parts = []
    for _, event in top_events:
        summary = event.get("summary")
        if summary:
            parts.append(summary)
        else:
            event_type = event.get("type", "unknown")
            source = event.get("source", event.get("actor", "someone"))
            target = event.get("target", "someone")
            parts.append(f"{source} {event_type} {target}")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]}, and {parts[1]}"
    return f"{parts[0]}, then {parts[1]}, then {parts[2]}"


def _select_key_events(
    events: List[Dict[str, Any]], max_events: int = 5
) -> List[Dict[str, Any]]:
    scored = [(compute_event_importance(e), e) for e in events]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:max_events]]


def _compute_ttl(importance: float) -> int:
    if importance >= 0.8:
        return 0
    if importance >= 0.6:
        return 200
    if importance >= 0.4:
        return 100
    if importance >= 0.2:
        return 50
    return 20


def chunk_events_into_episodes(
    events: List[Dict[str, Any]],
    chunk_size: int = 10,
    current_tick: int = 0,
) -> List[Episode]:
    """Split a batch of events into multiple episodes."""
    if len(events) <= chunk_size:
        return [EpisodeBuilder.from_events(events, current_tick)]
    episodes = []
    for i in range(0, len(events), chunk_size):
        chunk = events[i : i + chunk_size]
        episode = EpisodeBuilder.from_events(chunk, current_tick)
        episodes.append(episode)
    return episodes