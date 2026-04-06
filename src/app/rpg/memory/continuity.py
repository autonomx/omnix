"""Phase 11 — Memory / Continuity system.

Provides unified memory continuity across short-term conversation,
long-term actor memory, shared world / rumor memory, summarisation,
retrieval, NPC-decision influence, debug inspection, and determinism
validation.  All state is bounded and deterministic.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _safe_str(v: Any, default: str = "") -> str:
    return str(v) if v is not None else default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 11.0 — Memory state foundations
# ---------------------------------------------------------------------------

MAX_SHORT_TERM = 20
MAX_LONG_TERM = 200
MAX_WORLD_PER_ENTITY = 50
MAX_RUMORS = 30


@dataclass
class MemoryState:
    """Top-level bounded memory state container."""

    tick: int = 0
    short_term: List[Dict[str, Any]] = field(default_factory=list)
    long_term: List[Dict[str, Any]] = field(default_factory=list)
    world_memories: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    rumor_memories: List[Dict[str, Any]] = field(default_factory=list)

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "short_term": [dict(e) for e in self.short_term],
            "long_term": [dict(e) for e in self.long_term],
            "world_memories": {
                k: [dict(e) for e in v] for k, v in self.world_memories.items()
            },
            "rumor_memories": [dict(e) for e in self.rumor_memories],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryState":
        return cls(
            tick=_safe_int(d.get("tick"), 0),
            short_term=list(d.get("short_term") or []),
            long_term=list(d.get("long_term") or []),
            world_memories={
                k: list(v) for k, v in (d.get("world_memories") or {}).items()
            },
            rumor_memories=list(d.get("rumor_memories") or []),
        )


# ---------------------------------------------------------------------------
# 11.1 — Short-term conversational memory
# ---------------------------------------------------------------------------

class ConversationMemory:
    """Bounded short-term dialogue memory."""

    MAX_TURNS = MAX_SHORT_TERM
    DECAY_WINDOW = 10  # ticks before salience reduction

    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    def add_turn(self, speaker: str, text: str, tick: int) -> None:
        entry = {
            "speaker": _safe_str(speaker),
            "text": _safe_str(text),
            "tick": _safe_int(tick),
            "salience": 1.0,
        }
        self.entries.append(entry)
        if len(self.entries) > self.MAX_TURNS:
            self.entries = self.entries[-self.MAX_TURNS:]

    def get_recent(self, n: int = 5) -> List[Dict[str, Any]]:
        return list(self.entries[-n:])

    def decay(self, current_tick: int) -> None:
        for e in self.entries:
            age = current_tick - _safe_int(e.get("tick"), 0)
            if age > self.DECAY_WINDOW:
                e["salience"] = _clamp(e.get("salience", 1.0) * 0.8)

    def to_dict(self) -> Dict[str, Any]:
        return {"entries": [dict(e) for e in self.entries]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConversationMemory":
        cm = cls()
        cm.entries = list(d.get("entries") or [])
        return cm


# ---------------------------------------------------------------------------
# 11.2 — Long-term actor memory
# ---------------------------------------------------------------------------

class ActorMemory:
    """Per-actor long-term memory with salience scoring."""

    MAX_ENTRIES = MAX_LONG_TERM

    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    def record_event(self, actor_id: str, event: Dict[str, Any],
                     tick: int, salience: float = 0.5) -> None:
        entry = {
            "actor_id": _safe_str(actor_id),
            "event": dict(event),
            "tick": _safe_int(tick),
            "salience": _clamp(salience),
        }
        self.entries.append(entry)
        if len(self.entries) > self.MAX_ENTRIES:
            self.entries.sort(key=lambda e: e.get("salience", 0))
            self.entries = self.entries[len(self.entries) - self.MAX_ENTRIES:]

    def get_actor_memories(self, actor_id: str, top_k: int = 10) -> List[Dict[str, Any]]:
        actor = [e for e in self.entries if e.get("actor_id") == actor_id]
        actor.sort(key=lambda e: e.get("salience", 0), reverse=True)
        return actor[:top_k]

    def get_all_actors(self) -> List[str]:
        return sorted({e.get("actor_id", "") for e in self.entries})

    def decay(self, current_tick: int) -> None:
        for e in self.entries:
            age = current_tick - _safe_int(e.get("tick"), 0)
            if age > 0:
                factor = 0.95 ** age
                e["salience"] = _clamp(e.get("salience", 0.5) * factor)

    def to_dict(self) -> Dict[str, Any]:
        return {"entries": [dict(e) for e in self.entries]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActorMemory":
        am = cls()
        am.entries = list(d.get("entries") or [])
        return am


# ---------------------------------------------------------------------------
# 11.3 — Shared world memory / rumor memory
# ---------------------------------------------------------------------------

class WorldMemory:
    """Shared world events and rumor tracking."""

    MAX_WORLD = 50
    MAX_RUMORS = MAX_RUMORS

    def __init__(self) -> None:
        self.world_events: List[Dict[str, Any]] = []
        self.rumors: List[Dict[str, Any]] = []

    def record_world_event(self, event: Dict[str, Any], tick: int) -> None:
        entry = {"event": dict(event), "tick": _safe_int(tick), "salience": 0.7}
        self.world_events.append(entry)
        if len(self.world_events) > self.MAX_WORLD:
            self.world_events = self.world_events[-self.MAX_WORLD:]

    def record_rumor(self, rumor: Dict[str, Any], tick: int,
                     source_id: str = "", credibility: float = 0.5) -> None:
        entry = {
            "rumor": dict(rumor),
            "tick": _safe_int(tick),
            "source_id": _safe_str(source_id),
            "credibility": _clamp(credibility),
            "spread_count": 0,
        }
        self.rumors.append(entry)
        if len(self.rumors) > self.MAX_RUMORS:
            self.rumors.sort(key=lambda r: r.get("credibility", 0))
            self.rumors = self.rumors[len(self.rumors) - self.MAX_RUMORS:]

    def get_world_events(self, top_k: int = 10) -> List[Dict[str, Any]]:
        return list(self.world_events[-top_k:])

    def get_active_rumors(self) -> List[Dict[str, Any]]:
        return [r for r in self.rumors if r.get("credibility", 0) > 0.1]

    def decay_rumors(self, current_tick: int) -> None:
        for r in self.rumors:
            age = current_tick - _safe_int(r.get("tick"), 0)
            if age > 0:
                r["credibility"] = _clamp(r.get("credibility", 0.5) * 0.9)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_events": [dict(e) for e in self.world_events],
            "rumors": [dict(r) for r in self.rumors],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorldMemory":
        wm = cls()
        wm.world_events = list(d.get("world_events") or [])
        wm.rumors = list(d.get("rumors") or [])
        return wm


# ---------------------------------------------------------------------------
# 11.4 — Memory summarisation / compression
# ---------------------------------------------------------------------------

class MemoryCompressor:
    """Importance-based memory compression."""

    @staticmethod
    def compress_short_term(entries: List[Dict[str, Any]],
                            max_entries: int = 10) -> List[Dict[str, Any]]:
        if len(entries) <= max_entries:
            return list(entries)
        ranked = sorted(entries, key=lambda e: e.get("salience", 0), reverse=True)
        kept = ranked[:max_entries]
        dropped_count = len(entries) - max_entries
        kept.append({
            "type": "summary",
            "text": f"[{dropped_count} older conversation turns compressed]",
            "salience": 0.1,
        })
        return kept

    @staticmethod
    def compress_long_term(entries: List[Dict[str, Any]],
                           max_entries: int = 100) -> List[Dict[str, Any]]:
        if len(entries) <= max_entries:
            return list(entries)
        ranked = sorted(entries, key=lambda e: e.get("salience", 0), reverse=True)
        kept = ranked[:max_entries]
        dropped_count = len(entries) - max_entries
        kept.append({
            "type": "summary",
            "text": f"[{dropped_count} low-salience memories compressed]",
            "salience": 0.05,
        })
        return kept

    @staticmethod
    def compress_world(entries: List[Dict[str, Any]],
                       max_entries: int = 25) -> List[Dict[str, Any]]:
        if len(entries) <= max_entries:
            return list(entries)
        kept = entries[-max_entries:]
        dropped_count = len(entries) - max_entries
        kept.insert(0, {
            "type": "summary",
            "text": f"[{dropped_count} older world events compressed]",
            "salience": 0.1,
        })
        return kept


# ---------------------------------------------------------------------------
# 11.5 — Memory retrieval for runtime dialogue
# ---------------------------------------------------------------------------

class DialogueMemoryRetriever:
    """Retrieve memories relevant to a dialogue exchange."""

    @staticmethod
    def retrieve_for_dialogue(
        speaker_id: str,
        listener_id: str,
        topic: Optional[str] = None,
        tick: int = 0,
        memory_state: Optional[MemoryState] = None,
    ) -> List[Dict[str, Any]]:
        if memory_state is None:
            return []

        scored: List[tuple] = []

        # short-term
        for e in memory_state.short_term:
            score = 0.3
            if e.get("speaker") in (speaker_id, listener_id):
                score += 0.4
            if topic and topic.lower() in _safe_str(e.get("text")).lower():
                score += 0.3
            age = max(tick - _safe_int(e.get("tick")), 1)
            score *= 1.0 / (1.0 + age * 0.1)
            scored.append((score, e))

        # long-term actor memories
        for e in memory_state.long_term:
            score = 0.2
            if e.get("actor_id") in (speaker_id, listener_id):
                score += 0.5
            if topic:
                evt = e.get("event") or {}
                if topic.lower() in json.dumps(evt).lower():
                    score += 0.3
            score *= _safe_float(e.get("salience"), 0.5)
            scored.append((score, e))

        # world memories
        for _eid, entries in memory_state.world_memories.items():
            for e in entries:
                score = 0.15
                if topic:
                    evt = e.get("event") or {}
                    if topic.lower() in json.dumps(evt).lower():
                        score += 0.25
                score *= _safe_float(e.get("salience"), 0.5)
                scored.append((score, e))

        # rumors
        for r in memory_state.rumor_memories:
            score = 0.1 * _safe_float(r.get("credibility"), 0.5)
            if r.get("source_id") in (speaker_id, listener_id):
                score += 0.2
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:5]]


# ---------------------------------------------------------------------------
# 11.6 — Memory influence on NPC decisions
# ---------------------------------------------------------------------------

class MemoryInfluenceEngine:
    """Compute how memory affects NPC decision-making."""

    @staticmethod
    def compute_memory_influence(
        actor_id: str,
        decision_context: Dict[str, Any],
        memory_state: Optional[MemoryState] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "trust_modifier": 0.0,
            "fear_modifier": 0.0,
            "suggested_intent": None,
            "memory_tags": [],
        }
        if memory_state is None:
            return result

        # Scan long-term memories for this actor
        actor_mems = [
            e for e in memory_state.long_term
            if e.get("actor_id") == actor_id
        ]

        trust_sum = 0.0
        fear_sum = 0.0
        tags: List[str] = []

        for m in actor_mems:
            evt = m.get("event") or {}
            etype = _safe_str(evt.get("type"))
            salience = _safe_float(m.get("salience"), 0.5)

            if etype in ("help", "heal", "gift", "trade"):
                trust_sum += salience * 0.3
                tags.append("positive_interaction")
            elif etype in ("attack", "betray", "steal", "threaten"):
                fear_sum += salience * 0.3
                trust_sum -= salience * 0.2
                tags.append("negative_interaction")
            elif etype in ("observe", "dialogue"):
                trust_sum += salience * 0.05
                tags.append("neutral_interaction")

        target_id = _safe_str(decision_context.get("target_id"))
        if target_id:
            # Check memories involving target
            target_mems = [
                e for e in memory_state.long_term
                if (_safe_str((e.get("event") or {}).get("target_id")) == target_id
                    or _safe_str((e.get("event") or {}).get("actor")) == target_id)
            ]
            for m in target_mems:
                evt = m.get("event") or {}
                etype = _safe_str(evt.get("type"))
                if etype in ("attack", "betray"):
                    fear_sum += 0.15
                    tags.append("hostile_target_memory")

        result["trust_modifier"] = _clamp(trust_sum, -1.0, 1.0)
        result["fear_modifier"] = _clamp(fear_sum, -1.0, 1.0)

        # Suggest intent
        if fear_sum > 0.5:
            result["suggested_intent"] = "flee"
        elif trust_sum < -0.3:
            result["suggested_intent"] = "defend"
        elif trust_sum > 0.5:
            result["suggested_intent"] = "cooperate"

        result["memory_tags"] = sorted(set(tags))
        return result


# ---------------------------------------------------------------------------
# 11.7 — Memory inspector / debug tools
# ---------------------------------------------------------------------------

class MemoryInspector:
    """Debug inspection for memory state."""

    @staticmethod
    def inspect_memory_state(ms: MemoryState) -> Dict[str, Any]:
        return {
            "tick": ms.tick,
            "short_term_count": len(ms.short_term),
            "long_term_count": len(ms.long_term),
            "world_entity_count": len(ms.world_memories),
            "rumor_count": len(ms.rumor_memories),
            "total_world_entries": sum(
                len(v) for v in ms.world_memories.values()
            ),
        }

    @staticmethod
    def inspect_actor_memory(ms: MemoryState, actor_id: str) -> Dict[str, Any]:
        actor_entries = [
            e for e in ms.long_term if e.get("actor_id") == actor_id
        ]
        saliences = [_safe_float(e.get("salience")) for e in actor_entries]
        return {
            "actor_id": actor_id,
            "entry_count": len(actor_entries),
            "avg_salience": (sum(saliences) / len(saliences)) if saliences else 0.0,
            "max_salience": max(saliences) if saliences else 0.0,
            "min_salience": min(saliences) if saliences else 0.0,
        }

    @staticmethod
    def inspect_world_memory(ms: MemoryState) -> Dict[str, Any]:
        active_rumors = [
            r for r in ms.rumor_memories if _safe_float(r.get("credibility")) > 0.1
        ]
        return {
            "world_event_count": sum(len(v) for v in ms.world_memories.values()),
            "rumor_count": len(ms.rumor_memories),
            "active_rumor_count": len(active_rumors),
            "entities_tracked": sorted(ms.world_memories.keys()),
        }

    @staticmethod
    def get_memory_statistics(ms: MemoryState) -> Dict[str, Any]:
        all_saliences = []
        for e in ms.short_term:
            all_saliences.append(_safe_float(e.get("salience")))
        for e in ms.long_term:
            all_saliences.append(_safe_float(e.get("salience")))
        return {
            "total_entries": (
                len(ms.short_term)
                + len(ms.long_term)
                + sum(len(v) for v in ms.world_memories.values())
                + len(ms.rumor_memories)
            ),
            "avg_salience": (
                (sum(all_saliences) / len(all_saliences)) if all_saliences else 0.0
            ),
            "bounds": {
                "short_term_max": MAX_SHORT_TERM,
                "long_term_max": MAX_LONG_TERM,
                "world_per_entity_max": MAX_WORLD_PER_ENTITY,
                "rumors_max": MAX_RUMORS,
            },
        }


# ---------------------------------------------------------------------------
# 11.8 — Memory determinism / bounded-state fix pass
# ---------------------------------------------------------------------------

class MemoryDeterminismValidator:
    """Validate memory determinism and bounds."""

    @staticmethod
    def validate_determinism(s1: MemoryState, s2: MemoryState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(ms: MemoryState) -> List[str]:
        violations: List[str] = []
        if len(ms.short_term) > MAX_SHORT_TERM:
            violations.append(
                f"short_term exceeds max ({len(ms.short_term)} > {MAX_SHORT_TERM})"
            )
        if len(ms.long_term) > MAX_LONG_TERM:
            violations.append(
                f"long_term exceeds max ({len(ms.long_term)} > {MAX_LONG_TERM})"
            )
        if len(ms.rumor_memories) > MAX_RUMORS:
            violations.append(
                f"rumors exceeds max ({len(ms.rumor_memories)} > {MAX_RUMORS})"
            )
        for eid, entries in ms.world_memories.items():
            if len(entries) > MAX_WORLD_PER_ENTITY:
                violations.append(
                    f"world_memories[{eid}] exceeds max "
                    f"({len(entries)} > {MAX_WORLD_PER_ENTITY})"
                )
        for e in ms.short_term + ms.long_term:
            s = _safe_float(e.get("salience"))
            if s < 0.0 or s > 1.0:
                violations.append(f"salience out of range: {s}")
                break
        for r in ms.rumor_memories:
            c = _safe_float(r.get("credibility"))
            if c < 0.0 or c > 1.0:
                violations.append(f"credibility out of range: {c}")
                break
        return violations

    @staticmethod
    def normalize_state(ms: MemoryState) -> MemoryState:
        """Clamp all fields to valid bounds."""
        st = list(ms.short_term)
        if len(st) > MAX_SHORT_TERM:
            st = st[-MAX_SHORT_TERM:]
        for e in st:
            e["salience"] = _clamp(_safe_float(e.get("salience")))

        lt = list(ms.long_term)
        if len(lt) > MAX_LONG_TERM:
            lt.sort(key=lambda e: _safe_float(e.get("salience")), reverse=True)
            lt = lt[:MAX_LONG_TERM]
        for e in lt:
            e["salience"] = _clamp(_safe_float(e.get("salience")))

        wm: Dict[str, List[Dict[str, Any]]] = {}
        for eid, entries in ms.world_memories.items():
            trimmed = list(entries)
            if len(trimmed) > MAX_WORLD_PER_ENTITY:
                trimmed = trimmed[-MAX_WORLD_PER_ENTITY:]
            wm[eid] = trimmed

        rm = list(ms.rumor_memories)
        if len(rm) > MAX_RUMORS:
            rm.sort(key=lambda r: _safe_float(r.get("credibility")), reverse=True)
            rm = rm[:MAX_RUMORS]
        for r in rm:
            r["credibility"] = _clamp(_safe_float(r.get("credibility")))

        return MemoryState(
            tick=ms.tick,
            short_term=st,
            long_term=lt,
            world_memories=wm,
            rumor_memories=rm,
        )


# ---------------------------------------------------------------------------
# Unified façade
# ---------------------------------------------------------------------------

class MemoryContinuitySystem:
    """Unified façade over all Phase-11 sub-systems."""

    def __init__(self) -> None:
        self.conversation = ConversationMemory()
        self.actor_memory = ActorMemory()
        self.world_memory = WorldMemory()
        self.compressor = MemoryCompressor()
        self.retriever = DialogueMemoryRetriever()
        self.influence = MemoryInfluenceEngine()
        self.inspector = MemoryInspector()
        self.validator = MemoryDeterminismValidator()

    def build_memory_state(self, tick: int = 0) -> MemoryState:
        return MemoryState(
            tick=tick,
            short_term=list(self.conversation.entries),
            long_term=list(self.actor_memory.entries),
            world_memories=dict(self.world_memory.to_dict().get("world_events_by_entity", {})),
            rumor_memories=list(self.world_memory.rumors),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation": self.conversation.to_dict(),
            "actor_memory": self.actor_memory.to_dict(),
            "world_memory": self.world_memory.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryContinuitySystem":
        sys = cls()
        sys.conversation = ConversationMemory.from_dict(d.get("conversation") or {})
        sys.actor_memory = ActorMemory.from_dict(d.get("actor_memory") or {})
        sys.world_memory = WorldMemory.from_dict(d.get("world_memory") or {})
        return sys
