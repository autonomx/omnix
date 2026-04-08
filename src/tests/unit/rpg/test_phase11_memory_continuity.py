"""Phase 11 — Memory / Continuity system tests.

117 tests covering sub-phases 11.0 – 11.8.
"""
from __future__ import annotations

import copy
import os
import sys
import types

_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
for _mod_name, _rel_path in [
    ("app", "app"),
    ("app.rpg", os.path.join("app", "rpg")),
    ("app.rpg.memory", os.path.join("app", "rpg", "memory")),
]:
    if _mod_name not in sys.modules:
        _m = types.ModuleType(_mod_name)
        _m.__path__ = [os.path.join(_SRC_DIR, _rel_path)]
        sys.modules[_mod_name] = _m

from app.rpg.memory.continuity import (
    MAX_LONG_TERM,
    MAX_RUMORS,
    MAX_SHORT_TERM,
    MAX_WORLD_PER_ENTITY,
    ActorMemory,
    ConversationMemory,
    DialogueMemoryRetriever,
    MemoryCompressor,
    MemoryContinuitySystem,
    MemoryDeterminismValidator,
    MemoryInfluenceEngine,
    MemoryInspector,
    MemoryState,
    WorldMemory,
    _clamp,
    _safe_float,
    _safe_int,
    _safe_str,
)

# ── 11.0 MemoryState ────────────────────────────────────────────────────

class TestMemoryState:
    def test_default_construction(self):
        ms = MemoryState()
        assert ms.tick == 0
        assert ms.short_term == []
        assert ms.long_term == []
        assert ms.world_memories == {}
        assert ms.rumor_memories == []

    def test_round_trip(self):
        ms = MemoryState(tick=5, short_term=[{"a": 1}], long_term=[{"b": 2}],
                         world_memories={"e1": [{"c": 3}]},
                         rumor_memories=[{"d": 4}])
        d = ms.to_dict()
        ms2 = MemoryState.from_dict(d)
        assert ms2.to_dict() == d

    def test_from_dict_missing_keys(self):
        ms = MemoryState.from_dict({})
        assert ms.tick == 0
        assert ms.short_term == []

    def test_from_dict_bad_tick(self):
        ms = MemoryState.from_dict({"tick": "bad"})
        assert ms.tick == 0


# ── 11.1 ConversationMemory ─────────────────────────────────────────────

class TestConversationMemory:
    def test_add_turn(self):
        cm = ConversationMemory()
        cm.add_turn("alice", "hello", 1)
        assert len(cm.entries) == 1
        assert cm.entries[0]["speaker"] == "alice"

    def test_max_turns(self):
        cm = ConversationMemory()
        for i in range(30):
            cm.add_turn("s", f"msg{i}", i)
        assert len(cm.entries) == MAX_SHORT_TERM

    def test_get_recent(self):
        cm = ConversationMemory()
        for i in range(10):
            cm.add_turn("s", f"msg{i}", i)
        recent = cm.get_recent(3)
        assert len(recent) == 3
        assert recent[-1]["text"] == "msg9"

    def test_decay(self):
        cm = ConversationMemory()
        cm.add_turn("s", "old", 1)
        cm.decay(20)
        assert cm.entries[0]["salience"] < 1.0

    def test_no_decay_within_window(self):
        cm = ConversationMemory()
        cm.add_turn("s", "recent", 10)
        cm.decay(15)
        assert cm.entries[0]["salience"] == 1.0

    def test_round_trip(self):
        cm = ConversationMemory()
        cm.add_turn("a", "b", 1)
        cm2 = ConversationMemory.from_dict(cm.to_dict())
        assert cm2.entries == cm.entries

    def test_salience_clamped(self):
        cm = ConversationMemory()
        cm.add_turn("s", "t", 1)
        cm.entries[0]["salience"] = 2.0
        cm.decay(100)
        assert cm.entries[0]["salience"] <= 1.0


# ── 11.2 ActorMemory ────────────────────────────────────────────────────

class TestActorMemory:
    def test_record_event(self):
        am = ActorMemory()
        am.record_event("npc1", {"type": "attack"}, 1, 0.8)
        assert len(am.entries) == 1

    def test_max_entries(self):
        am = ActorMemory()
        for i in range(250):
            am.record_event("npc1", {"i": i}, i, salience=float(i) / 250)
        assert len(am.entries) <= MAX_LONG_TERM

    def test_get_actor_memories(self):
        am = ActorMemory()
        am.record_event("a", {"x": 1}, 1, 0.9)
        am.record_event("b", {"x": 2}, 2, 0.8)
        am.record_event("a", {"x": 3}, 3, 0.5)
        mems = am.get_actor_memories("a", top_k=5)
        assert len(mems) == 2
        assert mems[0]["salience"] >= mems[1]["salience"]

    def test_get_all_actors(self):
        am = ActorMemory()
        am.record_event("b", {}, 1)
        am.record_event("a", {}, 2)
        assert am.get_all_actors() == ["a", "b"]

    def test_decay(self):
        am = ActorMemory()
        am.record_event("a", {}, 1, 1.0)
        am.decay(10)
        assert am.entries[0]["salience"] < 1.0

    def test_round_trip(self):
        am = ActorMemory()
        am.record_event("a", {"t": "x"}, 1, 0.7)
        am2 = ActorMemory.from_dict(am.to_dict())
        assert am2.entries == am.entries

    def test_salience_clamped_on_record(self):
        am = ActorMemory()
        am.record_event("a", {}, 1, salience=5.0)
        assert am.entries[0]["salience"] <= 1.0

    def test_salience_clamped_negative(self):
        am = ActorMemory()
        am.record_event("a", {}, 1, salience=-1.0)
        assert am.entries[0]["salience"] >= 0.0


# ── 11.3 WorldMemory ────────────────────────────────────────────────────

class TestWorldMemory:
    def test_record_world_event(self):
        wm = WorldMemory()
        wm.record_world_event({"type": "earthquake"}, 1)
        assert len(wm.world_events) == 1

    def test_max_world_events(self):
        wm = WorldMemory()
        for i in range(60):
            wm.record_world_event({"i": i}, i)
        assert len(wm.world_events) <= 50

    def test_record_rumor(self):
        wm = WorldMemory()
        wm.record_rumor({"text": "secret"}, 1, "npc1", 0.8)
        assert len(wm.rumors) == 1
        assert wm.rumors[0]["credibility"] == 0.8

    def test_max_rumors(self):
        wm = WorldMemory()
        for i in range(40):
            wm.record_rumor({"i": i}, i, "s", float(i) / 40)
        assert len(wm.rumors) <= MAX_RUMORS

    def test_get_active_rumors(self):
        wm = WorldMemory()
        wm.record_rumor({"a": 1}, 1, "s", 0.8)
        wm.record_rumor({"b": 2}, 2, "s", 0.05)
        active = wm.get_active_rumors()
        assert len(active) == 1

    def test_decay_rumors(self):
        wm = WorldMemory()
        wm.record_rumor({"a": 1}, 1, "s", 0.8)
        wm.decay_rumors(20)
        assert wm.rumors[0]["credibility"] < 0.8

    def test_round_trip(self):
        wm = WorldMemory()
        wm.record_world_event({"t": "e"}, 1)
        wm.record_rumor({"r": 1}, 2, "s", 0.5)
        wm2 = WorldMemory.from_dict(wm.to_dict())
        assert wm2.to_dict() == wm.to_dict()

    def test_credibility_clamped(self):
        wm = WorldMemory()
        wm.record_rumor({}, 1, "s", credibility=5.0)
        assert wm.rumors[0]["credibility"] <= 1.0


# ── 11.4 MemoryCompressor ───────────────────────────────────────────────

class TestMemoryCompressor:
    def test_compress_short_term_under_limit(self):
        entries = [{"salience": 0.5}] * 5
        result = MemoryCompressor.compress_short_term(entries, 10)
        assert len(result) == 5

    def test_compress_short_term_over_limit(self):
        entries = [{"salience": float(i) / 20} for i in range(20)]
        result = MemoryCompressor.compress_short_term(entries, 5)
        assert len(result) == 6  # 5 kept + 1 summary
        summary = [e for e in result if e.get("type") == "summary"]
        assert len(summary) == 1

    def test_compress_long_term_under_limit(self):
        entries = [{"salience": 0.5}] * 50
        result = MemoryCompressor.compress_long_term(entries, 100)
        assert len(result) == 50

    def test_compress_long_term_over_limit(self):
        entries = [{"salience": float(i) / 200} for i in range(200)]
        result = MemoryCompressor.compress_long_term(entries, 50)
        assert len(result) == 51  # 50 kept + 1 summary

    def test_compress_world_under_limit(self):
        entries = [{"salience": 0.5}] * 10
        result = MemoryCompressor.compress_world(entries, 25)
        assert len(result) == 10

    def test_compress_world_over_limit(self):
        entries = [{"i": i} for i in range(30)]
        result = MemoryCompressor.compress_world(entries, 10)
        assert len(result) == 11  # 10 kept + 1 summary


# ── 11.5 DialogueMemoryRetriever ────────────────────────────────────────

class TestDialogueMemoryRetriever:
    def test_empty_state(self):
        result = DialogueMemoryRetriever.retrieve_for_dialogue("a", "b")
        assert result == []

    def test_none_state(self):
        result = DialogueMemoryRetriever.retrieve_for_dialogue(
            "a", "b", memory_state=None
        )
        assert result == []

    def test_retrieves_relevant(self):
        ms = MemoryState(
            short_term=[
                {"speaker": "alice", "text": "hello", "tick": 1, "salience": 0.8},
                {"speaker": "bob", "text": "weather", "tick": 2, "salience": 0.5},
            ],
            long_term=[
                {"actor_id": "alice", "event": {"type": "help"}, "tick": 1, "salience": 0.9},
            ],
        )
        result = DialogueMemoryRetriever.retrieve_for_dialogue(
            "alice", "bob", tick=3, memory_state=ms
        )
        assert len(result) > 0

    def test_topic_boost(self):
        ms = MemoryState(
            short_term=[
                {"speaker": "a", "text": "treasure map", "tick": 1, "salience": 0.5},
                {"speaker": "a", "text": "boring stuff", "tick": 1, "salience": 0.5},
            ]
        )
        result = DialogueMemoryRetriever.retrieve_for_dialogue(
            "a", "b", topic="treasure", tick=2, memory_state=ms
        )
        assert len(result) > 0

    def test_max_five_results(self):
        ms = MemoryState(
            short_term=[{"speaker": "a", "text": f"msg{i}", "tick": i, "salience": 0.5}
                        for i in range(20)]
        )
        result = DialogueMemoryRetriever.retrieve_for_dialogue(
            "a", "b", tick=21, memory_state=ms
        )
        assert len(result) <= 5


# ── 11.6 MemoryInfluenceEngine ──────────────────────────────────────────

class TestMemoryInfluenceEngine:
    def test_empty_state(self):
        result = MemoryInfluenceEngine.compute_memory_influence("a", {})
        assert result["trust_modifier"] == 0.0
        assert result["fear_modifier"] == 0.0
        assert result["suggested_intent"] is None

    def test_positive_interactions(self):
        ms = MemoryState(long_term=[
            {"actor_id": "npc1", "event": {"type": "help"}, "salience": 0.8, "tick": 1},
            {"actor_id": "npc1", "event": {"type": "heal"}, "salience": 0.9, "tick": 2},
        ])
        result = MemoryInfluenceEngine.compute_memory_influence(
            "npc1", {}, memory_state=ms
        )
        assert result["trust_modifier"] > 0
        assert "positive_interaction" in result["memory_tags"]

    def test_negative_interactions(self):
        ms = MemoryState(long_term=[
            {"actor_id": "npc1", "event": {"type": "attack"}, "salience": 0.9, "tick": 1},
            {"actor_id": "npc1", "event": {"type": "betray"}, "salience": 1.0, "tick": 2},
        ])
        result = MemoryInfluenceEngine.compute_memory_influence(
            "npc1", {}, memory_state=ms
        )
        assert result["fear_modifier"] > 0
        assert "negative_interaction" in result["memory_tags"]

    def test_fear_suggests_flee(self):
        ms = MemoryState(long_term=[
            {"actor_id": "npc1", "event": {"type": "attack"}, "salience": 1.0, "tick": i}
            for i in range(5)
        ])
        result = MemoryInfluenceEngine.compute_memory_influence(
            "npc1", {}, memory_state=ms
        )
        assert result["suggested_intent"] == "flee"

    def test_trust_suggests_cooperate(self):
        ms = MemoryState(long_term=[
            {"actor_id": "npc1", "event": {"type": "help"}, "salience": 1.0, "tick": i}
            for i in range(5)
        ])
        result = MemoryInfluenceEngine.compute_memory_influence(
            "npc1", {}, memory_state=ms
        )
        assert result["suggested_intent"] == "cooperate"

    def test_modifiers_clamped(self):
        ms = MemoryState(long_term=[
            {"actor_id": "a", "event": {"type": "help"}, "salience": 1.0, "tick": i}
            for i in range(100)
        ])
        result = MemoryInfluenceEngine.compute_memory_influence(
            "a", {}, memory_state=ms
        )
        assert -1.0 <= result["trust_modifier"] <= 1.0
        assert -1.0 <= result["fear_modifier"] <= 1.0


# ── 11.7 MemoryInspector ────────────────────────────────────────────────

class TestMemoryInspector:
    def test_inspect_memory_state(self):
        ms = MemoryState(tick=5, short_term=[{"a": 1}], long_term=[{"b": 2}],
                         world_memories={"e1": [{"c": 3}]},
                         rumor_memories=[{"d": 4}])
        info = MemoryInspector.inspect_memory_state(ms)
        assert info["tick"] == 5
        assert info["short_term_count"] == 1
        assert info["long_term_count"] == 1
        assert info["world_entity_count"] == 1
        assert info["rumor_count"] == 1

    def test_inspect_actor_memory(self):
        ms = MemoryState(long_term=[
            {"actor_id": "npc1", "salience": 0.8},
            {"actor_id": "npc1", "salience": 0.6},
            {"actor_id": "npc2", "salience": 0.5},
        ])
        info = MemoryInspector.inspect_actor_memory(ms, "npc1")
        assert info["actor_id"] == "npc1"
        assert info["entry_count"] == 2
        assert info["max_salience"] == 0.8

    def test_inspect_world_memory(self):
        ms = MemoryState(
            world_memories={"e1": [{"a": 1}]},
            rumor_memories=[{"credibility": 0.8}, {"credibility": 0.05}],
        )
        info = MemoryInspector.inspect_world_memory(ms)
        assert info["active_rumor_count"] == 1

    def test_get_memory_statistics(self):
        ms = MemoryState(short_term=[{"salience": 0.5}],
                         long_term=[{"salience": 0.7}])
        stats = MemoryInspector.get_memory_statistics(ms)
        assert stats["total_entries"] == 2
        assert stats["bounds"]["short_term_max"] == MAX_SHORT_TERM


# ── 11.8 MemoryDeterminismValidator ─────────────────────────────────────

class TestMemoryDeterminismValidator:
    def test_validate_determinism_equal(self):
        ms1 = MemoryState(tick=1, short_term=[{"a": 1}])
        ms2 = MemoryState(tick=1, short_term=[{"a": 1}])
        assert MemoryDeterminismValidator.validate_determinism(ms1, ms2)

    def test_validate_determinism_unequal(self):
        ms1 = MemoryState(tick=1)
        ms2 = MemoryState(tick=2)
        assert not MemoryDeterminismValidator.validate_determinism(ms1, ms2)

    def test_validate_bounds_ok(self):
        ms = MemoryState()
        assert MemoryDeterminismValidator.validate_bounds(ms) == []

    def test_validate_bounds_short_term_exceeded(self):
        ms = MemoryState(short_term=[{"salience": 0.5}] * 25)
        violations = MemoryDeterminismValidator.validate_bounds(ms)
        assert any("short_term" in v for v in violations)

    def test_validate_bounds_long_term_exceeded(self):
        ms = MemoryState(long_term=[{"salience": 0.5}] * 210)
        violations = MemoryDeterminismValidator.validate_bounds(ms)
        assert any("long_term" in v for v in violations)

    def test_validate_bounds_rumors_exceeded(self):
        ms = MemoryState(rumor_memories=[{"credibility": 0.5}] * 35)
        violations = MemoryDeterminismValidator.validate_bounds(ms)
        assert any("rumors" in v for v in violations)

    def test_validate_bounds_world_per_entity_exceeded(self):
        ms = MemoryState(world_memories={"e1": [{}] * 55})
        violations = MemoryDeterminismValidator.validate_bounds(ms)
        assert any("world_memories" in v for v in violations)

    def test_validate_bounds_salience_out_of_range(self):
        ms = MemoryState(short_term=[{"salience": 2.0}])
        violations = MemoryDeterminismValidator.validate_bounds(ms)
        assert any("salience" in v for v in violations)

    def test_validate_bounds_credibility_out_of_range(self):
        ms = MemoryState(rumor_memories=[{"credibility": -0.5}])
        violations = MemoryDeterminismValidator.validate_bounds(ms)
        assert any("credibility" in v for v in violations)

    def test_normalize_state_trims_short_term(self):
        ms = MemoryState(short_term=[{"salience": 0.5}] * 25)
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert len(norm.short_term) <= MAX_SHORT_TERM

    def test_normalize_state_trims_long_term(self):
        ms = MemoryState(long_term=[{"salience": 0.5}] * 210)
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert len(norm.long_term) <= MAX_LONG_TERM

    def test_normalize_state_trims_rumors(self):
        ms = MemoryState(rumor_memories=[{"credibility": 0.5}] * 35)
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert len(norm.rumor_memories) <= MAX_RUMORS

    def test_normalize_state_trims_world_per_entity(self):
        ms = MemoryState(world_memories={"e1": [{}] * 55})
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert len(norm.world_memories["e1"]) <= MAX_WORLD_PER_ENTITY

    def test_normalize_state_clamps_salience(self):
        ms = MemoryState(short_term=[{"salience": 2.0}])
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert norm.short_term[0]["salience"] <= 1.0

    def test_normalize_state_clamps_credibility(self):
        ms = MemoryState(rumor_memories=[{"credibility": -0.5}])
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert norm.rumor_memories[0]["credibility"] >= 0.0

    def test_normalize_preserves_tick(self):
        ms = MemoryState(tick=42)
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert norm.tick == 42

    def test_normalized_state_passes_bounds(self):
        ms = MemoryState(
            short_term=[{"salience": 5.0}] * 30,
            long_term=[{"salience": -1.0}] * 210,
            rumor_memories=[{"credibility": 2.0}] * 35,
            world_memories={"e1": [{}] * 55},
        )
        norm = MemoryDeterminismValidator.normalize_state(ms)
        assert MemoryDeterminismValidator.validate_bounds(norm) == []


# ── Helpers ──────────────────────────────────────────────────────────────

class TestHelpers:
    def test_clamp(self):
        assert _clamp(1.5) == 1.0
        assert _clamp(-0.5) == 0.0
        assert _clamp(0.5) == 0.5

    def test_safe_str(self):
        assert _safe_str(None) == ""
        assert _safe_str(42) == "42"

    def test_safe_float(self):
        assert _safe_float(None) == 0.0
        assert _safe_float("bad") == 0.0
        assert _safe_float("0.5") == 0.5

    def test_safe_int(self):
        assert _safe_int(None) == 0
        assert _safe_int("bad") == 0
        assert _safe_int("5") == 5


# ── Façade ───────────────────────────────────────────────────────────────

class TestMemoryContinuitySystem:
    def test_construction(self):
        sys = MemoryContinuitySystem()
        assert sys.conversation is not None
        assert sys.actor_memory is not None

    def test_build_memory_state(self):
        sys = MemoryContinuitySystem()
        sys.conversation.add_turn("a", "hello", 1)
        ms = sys.build_memory_state(tick=1)
        assert ms.tick == 1
        assert len(ms.short_term) == 1

    def test_serialisation_round_trip(self):
        sys = MemoryContinuitySystem()
        sys.conversation.add_turn("a", "b", 1)
        sys.actor_memory.record_event("npc1", {"type": "help"}, 1, 0.7)
        d = sys.to_dict()
        sys2 = MemoryContinuitySystem.from_dict(d)
        assert sys2.to_dict() == d

    def test_end_to_end_dialogue_retrieval(self):
        sys = MemoryContinuitySystem()
        sys.conversation.add_turn("alice", "hello", 1)
        sys.actor_memory.record_event("alice", {"type": "help"}, 1, 0.9)
        ms = sys.build_memory_state(tick=2)
        result = sys.retriever.retrieve_for_dialogue(
            "alice", "bob", tick=2, memory_state=ms
        )
        assert len(result) > 0

    def test_end_to_end_influence(self):
        sys = MemoryContinuitySystem()
        sys.actor_memory.record_event("npc1", {"type": "attack"}, 1, 1.0)
        sys.actor_memory.record_event("npc1", {"type": "attack"}, 2, 1.0)
        ms = sys.build_memory_state(tick=3)
        result = sys.influence.compute_memory_influence("npc1", {}, ms)
        assert result["fear_modifier"] > 0

    def test_end_to_end_inspect(self):
        sys = MemoryContinuitySystem()
        sys.conversation.add_turn("a", "b", 1)
        ms = sys.build_memory_state(tick=1)
        info = sys.inspector.inspect_memory_state(ms)
        assert info["short_term_count"] == 1

    def test_end_to_end_validate_and_normalize(self):
        sys = MemoryContinuitySystem()
        ms = MemoryState(short_term=[{"salience": 5.0}] * 30)
        norm = sys.validator.normalize_state(ms)
        assert sys.validator.validate_bounds(norm) == []


# ── Determinism ──────────────────────────────────────────────────────────

class TestDeterminism:
    def test_conversation_deterministic(self):
        c1, c2 = ConversationMemory(), ConversationMemory()
        for i in range(5):
            c1.add_turn("s", f"m{i}", i)
            c2.add_turn("s", f"m{i}", i)
        assert c1.to_dict() == c2.to_dict()

    def test_actor_memory_deterministic(self):
        a1, a2 = ActorMemory(), ActorMemory()
        for i in range(5):
            a1.record_event("a", {"i": i}, i, 0.5)
            a2.record_event("a", {"i": i}, i, 0.5)
        assert a1.to_dict() == a2.to_dict()

    def test_world_memory_deterministic(self):
        w1, w2 = WorldMemory(), WorldMemory()
        for i in range(5):
            w1.record_world_event({"i": i}, i)
            w2.record_world_event({"i": i}, i)
            w1.record_rumor({"r": i}, i, "s", 0.5)
            w2.record_rumor({"r": i}, i, "s", 0.5)
        assert w1.to_dict() == w2.to_dict()

    def test_compression_deterministic(self):
        entries = [{"salience": float(i) / 20} for i in range(20)]
        r1 = MemoryCompressor.compress_short_term(list(entries), 5)
        r2 = MemoryCompressor.compress_short_term(list(entries), 5)
        assert r1 == r2

    def test_retrieval_deterministic(self):
        ms = MemoryState(
            short_term=[{"speaker": "a", "text": "hello", "tick": 1, "salience": 0.8}],
            long_term=[{"actor_id": "a", "event": {"type": "help"}, "tick": 1, "salience": 0.9}],
        )
        r1 = DialogueMemoryRetriever.retrieve_for_dialogue("a", "b", tick=2, memory_state=ms)
        r2 = DialogueMemoryRetriever.retrieve_for_dialogue("a", "b", tick=2, memory_state=ms)
        assert r1 == r2

    def test_influence_deterministic(self):
        ms = MemoryState(long_term=[
            {"actor_id": "a", "event": {"type": "attack"}, "salience": 0.9, "tick": 1},
        ])
        r1 = MemoryInfluenceEngine.compute_memory_influence("a", {}, ms)
        r2 = MemoryInfluenceEngine.compute_memory_influence("a", {}, ms)
        assert r1 == r2

    def test_full_system_deterministic(self):
        def build():
            s = MemoryContinuitySystem()
            s.conversation.add_turn("a", "hello", 1)
            s.actor_memory.record_event("a", {"type": "help"}, 1, 0.8)
            s.world_memory.record_world_event({"type": "quake"}, 1)
            return s.to_dict()
        assert build() == build()

    def test_state_round_trip_determinism(self):
        ms = MemoryState(tick=5, short_term=[{"salience": 0.5, "speaker": "a"}])
        d = ms.to_dict()
        ms2 = MemoryState.from_dict(d)
        assert ms2.to_dict() == d
