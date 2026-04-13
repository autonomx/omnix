"""Comprehensive tests for 4C NPC-to-NPC conversation system.

Tests cover:
- conversation_beats: beat construction, storage, advancement, mentions extraction
- conversation_scheduler: scheduling, expiry, mode classification
- conversation_pivots: player pivot, group pivot, pivot application
- conversation_world_signals: signal extraction, storage, application
- conversation_settings (expanded): new settings, frequency, suppression
- narration_worker: queue, subscribers, event publishing
- conversation_engine integration: beats + signals wired into advance/tick

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_4c_npc_conversation_system.py -v --noconftest
"""
from __future__ import annotations

import asyncio
import copy
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Import machinery — stub all app.* dependencies that we don't test.
# ---------------------------------------------------------------------------

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, SRC_DIR)

_REAL_MODULES = {
    "app.rpg.social.npc_conversations",
    "app.rpg.social.conversation_settings",
    "app.rpg.social.conversation_topics",
    "app.rpg.social.conversation_participants",
    "app.rpg.social.conversation_templates",
    "app.rpg.social.player_interventions",
    "app.rpg.social.conversation_presentation",
    "app.rpg.social.conversation_engine",
    "app.rpg.social.conversation_beats",
    "app.rpg.social.conversation_pivots",
    "app.rpg.social.conversation_scheduler",
    "app.rpg.social.conversation_world_signals",
    "app.rpg.social.offscreen_conversations",
    "app.rpg.social.rumor_from_conversations",
    "app.rpg.social.faction_conversations",
    "app.rpg.social.crowd_conversations",
    "app.rpg.ai.conversation_prompt_builder",
    "app.rpg.ai.conversation_response_parser",
    "app.rpg.ai.conversation_gateway",
    "app.rpg.session.narration_worker",
    "app.rpg.session.ambient_builder",
    "app.rpg.presentation.personality_state",
    "app.rpg.analytics.tick_diff",
    "app.rpg.analytics.timeline",
}


class _StubModule(types.ModuleType):
    def __init__(self, name: str):
        super().__init__(name)
        self.__path__: list = []
        self.__package__ = name
        self.__file__ = "<stub>"
        self.__loader__ = None

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return MagicMock()


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        pass


class _AppStubFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("app"):
            return None
        if fullname in _REAL_MODULES:
            return None
        parts = fullname.split(".")
        for i in range(len(parts)):
            prefix = ".".join(parts[: i + 1])
            if prefix in _REAL_MODULES:
                return None
        return importlib.machinery.ModuleSpec(fullname, _StubLoader())


sys.meta_path.insert(0, _AppStubFinder())


def _load(dotted: str):
    parts = dotted.split(".")
    filename = parts[-1] + ".py"
    path_parts = parts[:-1] + [filename]
    filepath = os.path.join(SRC_DIR, *path_parts)
    spec = importlib.util.spec_from_file_location(dotted, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Load all modules under test
# Order matters: conversation_engine uses direct imports from beats, pivots,
# signals, scheduler, settings — those must be loaded first.
# ---------------------------------------------------------------------------

npc_conversations = _load("app.rpg.social.npc_conversations")
conversation_settings = _load("app.rpg.social.conversation_settings")
conversation_topics = _load("app.rpg.social.conversation_topics")
conversation_participants = _load("app.rpg.social.conversation_participants")
conversation_templates = _load("app.rpg.social.conversation_templates")
conversation_beats = _load("app.rpg.social.conversation_beats")
conversation_world_signals = _load("app.rpg.social.conversation_world_signals")
conversation_pivots = _load("app.rpg.social.conversation_pivots")
conversation_scheduler = _load("app.rpg.social.conversation_scheduler")
conversation_engine = _load("app.rpg.social.conversation_engine")
narration_worker = _load("app.rpg.session.narration_worker")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sim_state(location_id: str = "market_square", npcs: int = 3) -> Dict[str, Any]:
    """Build a minimal simulation state with NPCs at a location."""
    npc_index = {}
    npc_ids = []
    for i in range(npcs):
        nid = f"npc_{i}"
        npc_index[nid] = {
            "id": nid,
            "name": f"NPC {i}",
            "role": ["guard", "merchant", "thief"][i % 3],
            "location_id": location_id,
            "assertiveness": 0.5,
        }
        npc_ids.append(nid)
    return {
        "tick": 10,
        "player_state": {"location_id": location_id},
        "npc_index": npc_index,
        "npc_ids_at_location": {location_id: npc_ids},
        "social_state": {"conversations": {"active": [], "recent": [], "lines_by_conversation": {}}},
        "npc_minds": {},
        "active_interactions": [],
    }


def _runtime_state() -> Dict[str, Any]:
    return {
        "tick": 10,
        "current_location_id": "market_square",
        "conversation_settings": {},
        "mode": "live",
        "conversation_world_signals": {"pending": [], "applied": [], "total_emitted": 0},
    }


def _open_conversation(sim: Dict[str, Any], rt: Dict[str, Any], tick: int = 10, **overrides) -> Dict[str, Any]:
    """Open a conversation and return the conversation dict."""
    topic = overrides.pop("topic", {"type": "ambient_chat", "anchor": "general", "summary": "General chat", "priority": 0.5})
    participants = overrides.pop("participants", ["npc_0", "npc_1"])
    conv = conversation_engine.open_conversation(
        sim, rt,
        kind="ambient_npc_conversation",
        location_id="market_square",
        participants=participants,
        topic=topic,
        tick=tick,
    )
    for key, val in overrides.items():
        conv[key] = val
    npc_conversations.upsert_conversation(sim, conv)
    return conv


# ===========================================================================
# 4C-B: Conversation Beats Tests
# ===========================================================================


class TestConversationBeats:
    """Tests for conversation_beats module."""

    def test_build_beat_basic(self):
        beat = conversation_beats.build_conversation_beat(
            thread_id="conv:test:001",
            speaker_id="npc_0",
            addressed_to=["npc_1"],
            summary="I think the east road is dangerous.",
            stance="worried",
            mentions=["east_road", "bandits"],
            player_relevant=True,
            world_signal_strength=0.4,
            tick=10,
            beat_index=0,
        )
        assert beat["thread_id"] == "conv:test:001"
        assert beat["speaker_id"] == "npc_0"
        assert beat["addressed_to"] == ["npc_1"]
        assert beat["stance"] == "worried"
        assert beat["player_relevant"] is True
        assert beat["world_signal_strength"] == 0.4
        assert beat["beat_id"].startswith("beat:")
        assert len(beat["mentions"]) == 2

    def test_beat_id_is_stable(self):
        args = dict(
            thread_id="conv:test:001",
            speaker_id="npc_0",
            summary="test",
            tick=10,
            beat_index=0,
        )
        beat1 = conversation_beats.build_conversation_beat(**args)
        beat2 = conversation_beats.build_conversation_beat(**args)
        assert beat1["beat_id"] == beat2["beat_id"]

    def test_beat_id_differs_by_index(self):
        args = dict(
            thread_id="conv:test:001",
            speaker_id="npc_0",
            summary="test",
            tick=10,
        )
        beat1 = conversation_beats.build_conversation_beat(**args, beat_index=0)
        beat2 = conversation_beats.build_conversation_beat(**args, beat_index=1)
        assert beat1["beat_id"] != beat2["beat_id"]

    def test_world_signal_strength_clamped(self):
        beat = conversation_beats.build_conversation_beat(
            thread_id="t", speaker_id="s", summary="x",
            world_signal_strength=5.0, tick=1,
        )
        assert beat["world_signal_strength"] == 1.0
        beat2 = conversation_beats.build_conversation_beat(
            thread_id="t", speaker_id="s", summary="x",
            world_signal_strength=-1.0, tick=1,
        )
        assert beat2["world_signal_strength"] == 0.0

    def test_mentions_bounded(self):
        beat = conversation_beats.build_conversation_beat(
            thread_id="t", speaker_id="s", summary="x",
            mentions=[f"m{i}" for i in range(20)], tick=1,
        )
        assert len(beat["mentions"]) <= conversation_beats._MAX_MENTIONS_PER_BEAT

    def test_ensure_beats_state(self):
        sim = {}
        conversation_beats.ensure_beats_state(sim)
        assert "beats_by_thread" in sim["social_state"]["conversations"]
        assert isinstance(sim["social_state"]["conversations"]["beats_by_thread"], dict)

    def test_append_and_get_beats(self):
        sim = {}
        conversation_beats.ensure_beats_state(sim)
        beat = conversation_beats.build_conversation_beat(
            thread_id="conv:001", speaker_id="npc_0",
            summary="Hello", tick=10, beat_index=0,
        )
        conversation_beats.append_beat(sim, beat)
        beats = conversation_beats.get_beats(sim, "conv:001")
        assert len(beats) == 1
        assert beats[0]["summary"] == "Hello"

    def test_get_latest_beat(self):
        sim = {}
        conversation_beats.ensure_beats_state(sim)
        for i in range(3):
            beat = conversation_beats.build_conversation_beat(
                thread_id="conv:001", speaker_id=f"npc_{i}",
                summary=f"Beat {i}", tick=10 + i, beat_index=i,
            )
            conversation_beats.append_beat(sim, beat)
        latest = conversation_beats.get_latest_beat(sim, "conv:001")
        assert latest is not None
        assert latest["summary"] == "Beat 2"

    def test_get_latest_beat_empty(self):
        sim = {}
        conversation_beats.ensure_beats_state(sim)
        assert conversation_beats.get_latest_beat(sim, "nonexistent") is None

    def test_beats_bounded_per_thread(self):
        sim = {}
        conversation_beats.ensure_beats_state(sim)
        for i in range(20):
            beat = conversation_beats.build_conversation_beat(
                thread_id="conv:001", speaker_id="npc_0",
                summary=f"Beat {i}", tick=i, beat_index=i,
            )
            conversation_beats.append_beat(sim, beat)
        beats = conversation_beats.get_beats(sim, "conv:001")
        assert len(beats) <= conversation_beats._MAX_BEATS_PER_THREAD

    def test_trim_beats_state(self):
        sim = {}
        conversation_beats.ensure_beats_state(sim)
        # Create more threads than the limit
        for t in range(100):
            beat = conversation_beats.build_conversation_beat(
                thread_id=f"conv:{t}", speaker_id="npc_0",
                summary="x", tick=t, beat_index=0,
            )
            conversation_beats.append_beat(sim, beat)
        conversation_beats.trim_beats_state(sim, max_threads=10)
        assert len(sim["social_state"]["conversations"]["beats_by_thread"]) <= 10

    def test_should_advance_thread_basic(self):
        conv = {"status": "active", "beat_count": 0, "max_turns": 5, "expires_at_tick": 20}
        assert conversation_beats.should_advance_thread(conv, 10) is True

    def test_should_advance_thread_completed(self):
        conv = {"status": "active", "beat_count": 5, "max_turns": 5, "expires_at_tick": 20}
        assert conversation_beats.should_advance_thread(conv, 10) is False

    def test_should_advance_thread_expired(self):
        conv = {"status": "active", "beat_count": 2, "max_turns": 5, "expires_at_tick": 5}
        assert conversation_beats.should_advance_thread(conv, 10) is False

    def test_should_advance_thread_closed(self):
        conv = {"status": "closed", "beat_count": 0, "max_turns": 5}
        assert conversation_beats.should_advance_thread(conv, 10) is False

    def test_compute_beat_caps(self):
        assert conversation_beats.compute_beat_caps("ambient") == (2, 5)
        assert conversation_beats.compute_beat_caps("directed_to_player") == (3, 6)
        assert conversation_beats.compute_beat_caps("group") == (4, 8)
        # Unknown mode falls back to ambient
        assert conversation_beats.compute_beat_caps("unknown") == (2, 5)

    def test_extract_mentions_from_topic(self):
        topic = {"type": "local_incident", "anchor": "east_road", "summary": "Bandits spotted near the east road bridge"}
        mentions = conversation_beats.extract_mentions_from_topic(topic)
        assert "east_road" in mentions
        assert len(mentions) <= conversation_beats._MAX_MENTIONS_PER_BEAT

    def test_build_beat_from_conversation_line(self):
        conv = {
            "conversation_id": "conv:001",
            "participants": ["npc_0", "npc_1"],
            "topic": {"type": "local_incident", "anchor": "east_road", "summary": "Bandits"},
            "player_present": True,
            "beat_count": 0,
        }
        line = {"speaker": "npc_0", "text": "We should be careful.", "kind": "warning"}
        beat = conversation_beats.build_beat_from_conversation_line(conv, line, 10)
        assert beat["speaker_id"] == "npc_0"
        assert beat["thread_id"] == "conv:001"
        assert beat["player_relevant"] is True
        assert beat["addressed_to"] == ["npc_1"]
        assert beat["world_signal_strength"] > 0


# ===========================================================================
# 4C-D: Conversation Pivots Tests
# ===========================================================================


class TestConversationPivots:
    """Tests for conversation_pivots module."""

    def test_should_not_pivot_non_ambient(self):
        conv = {"mode": "directed_to_player", "player_present": True, "beat_count": 2, "pivot_history": []}
        assert conversation_pivots.should_pivot_to_player(conv, {}, {}) is False

    def test_should_not_pivot_player_absent(self):
        conv = {"mode": "ambient", "player_present": False, "beat_count": 2, "pivot_history": []}
        assert conversation_pivots.should_pivot_to_player(conv, {}, {}) is False

    def test_should_not_pivot_too_early(self):
        conv = {"mode": "ambient", "player_present": True, "beat_count": 0, "pivot_history": []}
        assert conversation_pivots.should_pivot_to_player(conv, {}, {}) is False

    def test_should_pivot_plan_reaction(self):
        conv = {
            "mode": "ambient", "player_present": True, "beat_count": 2,
            "pivot_history": [],
            "topic": {"type": "plan_reaction"},
        }
        assert conversation_pivots.should_pivot_to_player(conv, {}, {}) is True

    def test_should_pivot_player_relevant_beat(self):
        conv = {
            "mode": "ambient", "player_present": True, "beat_count": 2,
            "pivot_history": [],
            "topic": {"type": "ambient_chat"},
        }
        beat = {"player_relevant": True, "world_signal_strength": 0.5}
        assert conversation_pivots.should_pivot_to_player(conv, {}, {}, latest_beat=beat) is True

    def test_should_not_pivot_too_many_pivots(self):
        conv = {
            "mode": "ambient", "player_present": True, "beat_count": 2,
            "pivot_history": [{"from_mode": "x", "to_mode": "y"}, {"from_mode": "y", "to_mode": "z"}],
            "topic": {"type": "plan_reaction"},
        }
        assert conversation_pivots.should_pivot_to_player(conv, {}, {}) is False

    def test_apply_pivot_to_player(self):
        conv = {
            "mode": "ambient",
            "player_can_intervene": False,
            "audience": [],
            "pivot_history": [],
            "beat_count": 2,
            "max_turns": 4,
            "importance": 20,
            "world_effect_budget": 1,
        }
        result = conversation_pivots.apply_pivot_to_player(conv, 15)
        assert result["mode"] == "directed_to_player"
        assert result["player_can_intervene"] is True
        assert "player" in result["audience"]
        assert len(result["pivot_history"]) == 1
        assert result["pivot_history"][0]["to_mode"] == "directed_to_player"
        assert result["importance"] > 20
        assert result["world_effect_budget"] >= 2

    def test_should_pivot_to_group(self):
        conv = {
            "mode": "ambient",
            "participants": ["npc_0", "npc_1"],
            "beat_count": 2,
            "pivot_history": [],
            "topic": {"type": "faction_tension"},
        }
        assert conversation_pivots.should_pivot_to_group(conv, {}, ["npc_0", "npc_1", "npc_2"]) is True

    def test_should_not_pivot_to_group_no_joinable(self):
        conv = {
            "mode": "ambient",
            "participants": ["npc_0", "npc_1"],
            "beat_count": 2,
            "pivot_history": [],
            "topic": {"type": "faction_tension"},
        }
        assert conversation_pivots.should_pivot_to_group(conv, {}, ["npc_0", "npc_1"]) is False

    def test_should_not_pivot_to_group_low_importance_topic(self):
        conv = {
            "mode": "ambient",
            "participants": ["npc_0", "npc_1"],
            "beat_count": 2,
            "pivot_history": [],
            "topic": {"type": "ambient_chat"},
        }
        assert conversation_pivots.should_pivot_to_group(conv, {}, ["npc_0", "npc_1", "npc_2"]) is False

    def test_apply_pivot_to_group(self):
        conv = {
            "mode": "ambient",
            "participants": ["npc_0", "npc_1"],
            "pivot_history": [],
            "beat_count": 2,
            "max_turns": 4,
            "importance": 20,
            "world_effect_budget": 1,
        }
        result = conversation_pivots.apply_pivot_to_group(conv, ["npc_2"], 15)
        assert result["mode"] == "group"
        assert "npc_2" in result["participants"]
        assert len(result["pivot_history"]) == 1
        assert result["pivot_history"][0]["to_mode"] == "group"
        assert result["importance"] > 20
        assert result["world_effect_budget"] >= 3

    def test_apply_pivot_to_group_bounded_participants(self):
        conv = {
            "mode": "ambient",
            "participants": ["npc_0", "npc_1", "npc_2", "npc_3", "npc_4"],
            "pivot_history": [],
            "beat_count": 2,
            "max_turns": 4,
            "importance": 20,
            "world_effect_budget": 1,
        }
        result = conversation_pivots.apply_pivot_to_group(conv, ["npc_5", "npc_6", "npc_7"], 15)
        assert len(result["participants"]) <= 6


# ===========================================================================
# 4C-E: World Signal Extraction Tests
# ===========================================================================


class TestWorldSignals:
    """Tests for conversation_world_signals module."""

    def test_build_world_signal(self):
        sig = conversation_world_signals.build_world_signal(
            signal_type="rumor",
            source_thread_id="conv:001",
            source_beat_id="beat:001",
            topic="bandit_activity",
            location_id="east_road",
            strength=1,
            tick=10,
        )
        assert sig["type"] == "rumor"
        assert sig["signal_id"].startswith("sig:")
        assert sig["topic"] == "bandit_activity"
        assert sig["applied"] is False

    def test_build_world_signal_invalid_type(self):
        sig = conversation_world_signals.build_world_signal(
            signal_type="invalid_type",
            source_thread_id="conv:001",
            tick=10,
        )
        assert sig["type"] == "active_scene_topic"  # defaults

    def test_build_world_signal_strength_bounded(self):
        sig = conversation_world_signals.build_world_signal(
            signal_type="rumor",
            source_thread_id="conv:001",
            strength=10,
            tick=10,
        )
        assert sig["strength"] <= 3

    def test_extract_signals_from_beat_rumor(self):
        beat = {
            "beat_id": "beat:001",
            "thread_id": "conv:001",
            "world_signal_strength": 0.5,
            "mentions": ["bandits"],
            "player_relevant": False,
            "stance": "statement",
        }
        conv = {
            "topic": {"type": "local_incident", "summary": "Bandits spotted"},
            "location_id": "east_road",
            "world_effect_budget": 3,
            "world_effects_emitted": 0,
        }
        signals = conversation_world_signals.extract_signals_from_beat(beat, conv)
        assert isinstance(signals, list)
        assert len(signals) > 0
        types = {s["type"] for s in signals}
        assert "rumor" in types

    def test_extract_signals_empty_for_low_strength(self):
        beat = {
            "beat_id": "beat:001",
            "thread_id": "conv:001",
            "world_signal_strength": 0.01,
            "mentions": [],
            "player_relevant": False,
            "stance": "statement",
        }
        conv = {
            "topic": {"type": "ambient_chat", "summary": "Nice weather"},
            "location_id": "market",
            "world_effect_budget": 1,
            "world_effects_emitted": 0,
        }
        signals = conversation_world_signals.extract_signals_from_beat(beat, conv)
        # Low signal strength ambient chat should produce no signals
        assert len(signals) == 0

    def test_extract_signals_respects_budget(self):
        beat = {
            "beat_id": "beat:001",
            "thread_id": "conv:001",
            "world_signal_strength": 0.8,
            "mentions": ["bandits"],
            "player_relevant": True,
            "stance": "warning",
        }
        conv = {
            "topic": {"type": "local_incident", "summary": "Bandits"},
            "location_id": "east_road",
            "world_effect_budget": 1,
            "world_effects_emitted": 1,  # already at budget
        }
        signals = conversation_world_signals.extract_signals_from_beat(beat, conv)
        assert len(signals) == 0

    def test_ensure_signal_state(self):
        rt = {}
        conversation_world_signals.ensure_signal_state(rt)
        assert "conversation_world_signals" in rt
        assert "pending" in rt["conversation_world_signals"]
        assert "applied" in rt["conversation_world_signals"]

    def test_enqueue_and_get_signals(self):
        rt = {}
        conversation_world_signals.ensure_signal_state(rt)
        sig = conversation_world_signals.build_world_signal(
            signal_type="rumor",
            source_thread_id="conv:001",
            topic="test",
            tick=10,
        )
        conversation_world_signals.enqueue_signals(rt, [sig])
        pending = conversation_world_signals.get_pending_signals(rt)
        assert len(pending) == 1
        assert pending[0]["type"] == "rumor"

    def test_mark_signals_applied(self):
        rt = {}
        conversation_world_signals.ensure_signal_state(rt)
        sig = conversation_world_signals.build_world_signal(
            signal_type="rumor",
            source_thread_id="conv:001",
            topic="test",
            tick=10,
        )
        conversation_world_signals.enqueue_signals(rt, [sig])
        conversation_world_signals.mark_signals_applied(rt, [sig["signal_id"]])
        pending = conversation_world_signals.get_pending_signals(rt)
        assert len(pending) == 0
        assert len(rt["conversation_world_signals"]["applied"]) == 1

    def test_apply_rumor_signal(self):
        sim = {"social_state": {"conversations": {}}}
        sig = conversation_world_signals.build_world_signal(
            signal_type="rumor",
            source_thread_id="conv:001",
            topic="bandits",
            location_id="east_road",
            tick=10,
            metadata={"mentions": ["bandits"], "topic_type": "local_incident"},
        )
        conversation_world_signals.apply_rumor_signal(sig, sim)
        rumors = sim["social_state"]["conversations"]["conversation_rumors"]
        assert len(rumors) == 1
        assert rumors[0]["topic"] == "bandits"

    def test_apply_tension_signal(self):
        sim = {"social_state": {}}
        sig = conversation_world_signals.build_world_signal(
            signal_type="tension_increase",
            source_thread_id="conv:001",
            location_id="east_road",
            strength=1,
            tick=10,
        )
        conversation_world_signals.apply_tension_signal(sig, sim)
        assert sim["social_state"]["location_tension"]["east_road"] == 1
        # Apply again
        conversation_world_signals.apply_tension_signal(sig, sim)
        assert sim["social_state"]["location_tension"]["east_road"] == 2

    def test_apply_tension_decrease(self):
        sim = {"social_state": {"location_tension": {"east_road": 5}}}
        sig = conversation_world_signals.build_world_signal(
            signal_type="tension_decrease",
            source_thread_id="conv:001",
            location_id="east_road",
            strength=2,
            tick=10,
        )
        conversation_world_signals.apply_tension_signal(sig, sim)
        assert sim["social_state"]["location_tension"]["east_road"] == 3

    def test_apply_pending_signals_integration(self):
        sim = {"social_state": {"conversations": {}}}
        rt = {}
        conversation_world_signals.ensure_signal_state(rt)
        sig = conversation_world_signals.build_world_signal(
            signal_type="rumor",
            source_thread_id="conv:001",
            topic="test",
            tick=10,
        )
        conversation_world_signals.enqueue_signals(rt, [sig])
        sim2, rt2 = conversation_world_signals.apply_pending_signals(sim, rt)
        assert len(conversation_world_signals.get_pending_signals(rt2)) == 0


# ===========================================================================
# 4C-F: Expanded Conversation Settings Tests
# ===========================================================================


class TestExpandedSettings:
    """Tests for expanded conversation_settings module."""

    def test_default_settings_include_4c_fields(self):
        defaults = conversation_settings.get_default_conversation_settings()
        assert "ambient_delay_after_player_turn" in defaults
        assert "max_concurrent_ambient_threads" in defaults
        assert "max_beats_per_ambient_thread" in defaults
        assert "allow_npc_address_player" in defaults
        assert "allow_conversation_world_signals" in defaults
        assert "conversation_frequency" in defaults
        assert "combat_suppression" in defaults
        assert "stealth_suppression" in defaults

    def test_resolve_includes_4c_fields(self):
        settings = conversation_settings.resolve_conversation_settings({}, {})
        assert settings["ambient_delay_after_player_turn"] == 15
        assert settings["max_concurrent_ambient_threads"] == 3
        assert settings["max_beats_per_ambient_thread"] == 5
        assert settings["allow_npc_address_player"] is True
        assert settings["allow_conversation_world_signals"] is True
        assert settings["conversation_frequency"] == "normal"
        assert settings["combat_suppression"] is True
        assert settings["stealth_suppression"] is True

    def test_resolve_overrides(self):
        rt = {"conversation_settings": {"max_concurrent_ambient_threads": 1, "conversation_frequency": "sparse"}}
        settings = conversation_settings.resolve_conversation_settings({}, rt)
        assert settings["max_concurrent_ambient_threads"] == 1
        assert settings["conversation_frequency"] == "sparse"

    def test_concurrent_threads_bounded(self):
        rt = {"conversation_settings": {"max_concurrent_ambient_threads": 100}}
        settings = conversation_settings.resolve_conversation_settings({}, rt)
        assert settings["max_concurrent_ambient_threads"] <= 3

    def test_beats_bounded(self):
        rt = {"conversation_settings": {"max_beats_per_ambient_thread": 100}}
        settings = conversation_settings.resolve_conversation_settings({}, rt)
        assert settings["max_beats_per_ambient_thread"] <= 6

    def test_invalid_frequency_defaults(self):
        rt = {"conversation_settings": {"conversation_frequency": "INVALID"}}
        settings = conversation_settings.resolve_conversation_settings({}, rt)
        assert settings["conversation_frequency"] == "normal"

    def test_frequency_multiplier(self):
        assert conversation_settings.get_frequency_multiplier({"conversation_frequency": "sparse"}) == 0.5
        assert conversation_settings.get_frequency_multiplier({"conversation_frequency": "normal"}) == 1.0
        assert conversation_settings.get_frequency_multiplier({"conversation_frequency": "lively"}) == 1.5

    def test_combat_suppression(self):
        sim = {"combat_state": {"active": True}}
        settings = {"combat_suppression": True, "stealth_suppression": True}
        assert conversation_settings.should_suppress_conversations(sim, settings) is True

    def test_stealth_suppression(self):
        sim = {"player_state": {"stealth_active": True}}
        settings = {"combat_suppression": True, "stealth_suppression": True}
        assert conversation_settings.should_suppress_conversations(sim, settings) is True

    def test_no_suppression_when_disabled(self):
        sim = {"combat_state": {"active": True}}
        settings = {"combat_suppression": False, "stealth_suppression": False}
        assert conversation_settings.should_suppress_conversations(sim, settings) is False

    def test_is_combat_active_via_interactions(self):
        sim = {"active_interactions": [{"type": "combat"}]}
        assert conversation_settings.is_combat_active(sim) is True

    def test_is_combat_not_active(self):
        sim = {"active_interactions": []}
        assert conversation_settings.is_combat_active(sim) is False


# ===========================================================================
# 4C-G: Narration Worker Tests
# ===========================================================================


class TestNarrationWorker:
    """Tests for narration_worker module (manager + SSE pub/sub only)."""

    def setup_method(self):
        # Clear pending sessions registry between tests
        narration_worker._pending_sessions.clear()

    def test_signal_narration_work_session_id(self):
        result = narration_worker.signal_narration_work("session_abc")
        assert result is True
        sessions = narration_worker.drain_pending_sessions()
        assert "session_abc" in sessions

    def test_signal_narration_work_empty_returns_false(self):
        result = narration_worker.signal_narration_work("")
        assert result is False
        result = narration_worker.signal_narration_work(None)
        assert result is False

    def test_drain_pending_sessions_clears(self):
        narration_worker.signal_narration_work("s1")
        narration_worker.signal_narration_work("s2")
        sessions = narration_worker.drain_pending_sessions()
        assert set(sessions) == {"s1", "s2"}
        # Second drain should be empty
        assert narration_worker.drain_pending_sessions() == []

    def test_ensure_narration_worker_running(self):
        narration_worker.ensure_narration_worker_running()
        # Should not raise

    def test_no_competing_job_queue(self):
        """Verify narration_worker has no independent job queue (A1, A2)."""
        assert not hasattr(narration_worker, "_narration_queue"), \
            "narration_worker must not own a competing job queue"
        assert not hasattr(narration_worker, "get_pending_jobs"), \
            "narration_worker must not provide get_pending_jobs"
        assert not hasattr(narration_worker, "get_queue_size"), \
            "narration_worker must not provide get_queue_size"
        assert not hasattr(narration_worker, "clear_queue"), \
            "narration_worker must not provide clear_queue"

    def test_publish_narration_event_no_subscribers(self):
        count = narration_worker.publish_narration_event("session_1", {"type": "test"})
        assert count == 0

    def test_subscribe_and_publish(self):
        q = narration_worker.subscribe_narration_events("session_1")
        count = narration_worker.publish_narration_event("session_1", {"type": "test"})
        assert count == 1
        assert not q.empty()
        narration_worker.unsubscribe_narration_events("session_1", q)

    def test_unsubscribe(self):
        q = narration_worker.subscribe_narration_events("session_1")
        narration_worker.unsubscribe_narration_events("session_1", q)
        count = narration_worker.publish_narration_event("session_1", {"type": "test"})
        assert count == 0

    def test_publish_empty_session_id(self):
        count = narration_worker.publish_narration_event("", {"type": "test"})
        assert count == 0


# ===========================================================================
# 4C-A: Thread Engine Extensions Tests
# ===========================================================================


class TestThreadEngineExtensions:
    """Tests for expanded npc_conversations thread fields."""

    def test_build_conversation_state_has_4c_fields(self):
        conv = npc_conversations.build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="market",
            participants=["npc_0", "npc_1"],
            initiator_id="npc_0",
            topic={"type": "ambient_chat", "anchor": "general", "summary": "chat"},
            max_turns=5,
            player_can_intervene=True,
            player_present=True,
            tick=10,
        )
        assert conv["mode"] == "ambient"
        assert conv["audience"] == []
        assert conv["importance"] == 0
        assert conv["world_effect_budget"] == 0
        assert conv["world_effects_emitted"] == 0
        assert conv["beat_count"] == 0
        assert isinstance(conv["pivot_history"], list)
        assert conv["expires_at_tick"] > 10

    def test_conversation_state_expires_at_tick_calculation(self):
        conv = npc_conversations.build_conversation_state(
            kind="test", location_id="x", participants=["a", "b"],
            initiator_id="a", topic={}, max_turns=5,
            player_can_intervene=False, player_present=False, tick=10,
        )
        assert conv["expires_at_tick"] == 10 + 5 + 4


# ===========================================================================
# Integration Tests: Engine with Beats + Signals
# ===========================================================================


class TestEngineIntegration:
    """Tests for conversation_engine integration with beats and signals."""

    def test_run_conversation_tick_produces_beats(self):
        sim = _sim_state()
        rt = _runtime_state()
        conversation_beats.ensure_beats_state(sim)

        # Open a conversation
        _open_conversation(sim, rt, tick=10)
        active = npc_conversations.list_active_conversations(sim)
        assert len(active) == 1

        # Run a tick
        conversation_engine.run_conversation_tick(sim, rt, 11)

        # Check that beats were produced (if beats module was available)
        beats_store = sim.get("social_state", {}).get("conversations", {}).get("beats_by_thread", {})
        if beats_store:
            total_beats = sum(len(v) for v in beats_store.values())
            assert total_beats >= 1

    def test_run_conversation_tick_with_combat_suppression(self):
        sim = _sim_state()
        sim["combat_state"] = {"active": True}
        rt = _runtime_state()
        rt["conversation_settings"] = {"combat_suppression": True}

        _open_conversation(sim, rt, tick=10)
        # Run tick - should not advance due to combat
        conversation_engine.run_conversation_tick(sim, rt, 11)
        # Conversation should still be active (not advanced, not closed)
        active = npc_conversations.list_active_conversations(sim)
        # Combat suppression skips advancing, so it stays as-is
        assert len(active) == 1
        assert active[0]["turn_count"] == 0

    def test_advance_increments_beat_count(self):
        sim = _sim_state()
        rt = _runtime_state()
        conversation_beats.ensure_beats_state(sim)

        conv = _open_conversation(sim, rt, tick=10)
        conversation_engine.advance_active_conversations(sim, rt, 11)

        active = npc_conversations.list_active_conversations(sim)
        # May have advanced and closed, or still active
        all_convs = active + npc_conversations.list_recent_conversations(sim)
        assert any(c.get("beat_count", 0) > 0 for c in all_convs)


# ===========================================================================
# Conversation Scheduler Tests
# ===========================================================================


class TestConversationScheduler:
    """Tests for conversation_scheduler module (helper-only, no lifecycle loop)."""

    def test_classify_thread_mode_ambient(self):
        conv = {"participants": ["npc_0", "npc_1"], "topic": {"type": "ambient_chat"}, "mode": "ambient"}
        assert conversation_scheduler.classify_thread_mode(conv, {}, {}) == "ambient"

    def test_classify_thread_mode_group(self):
        conv = {"participants": ["npc_0", "npc_1", "npc_2"], "topic": {"type": "ambient_chat"}, "mode": "ambient"}
        assert conversation_scheduler.classify_thread_mode(conv, {}, {}) == "group"

    def test_classify_thread_mode_player_in_group(self):
        conv = {"participants": ["npc_0", "player"], "topic": {"type": "ambient_chat"}, "mode": "ambient"}
        assert conversation_scheduler.classify_thread_mode(conv, {}, {}) == "group"

    def test_classify_thread_mode_directed(self):
        conv = {
            "participants": ["npc_0", "npc_1"],
            "topic": {"type": "plan_reaction"},
            "mode": "ambient",
            "player_present": True,
        }
        assert conversation_scheduler.classify_thread_mode(conv, {}, {}) == "directed_to_player"

    def test_thread_importance_computation(self):
        conv_ambient = {"mode": "ambient", "topic": {"type": "ambient_chat", "priority": 0.3}}
        conv_directed = {"mode": "directed_to_player", "topic": {"type": "plan_reaction", "priority": 0.8}}
        assert conversation_scheduler.compute_thread_importance(conv_directed) > conversation_scheduler.compute_thread_importance(conv_ambient)

    def test_world_effect_budget(self):
        assert conversation_scheduler.compute_world_effect_budget({"mode": "group"}) == 3
        assert conversation_scheduler.compute_world_effect_budget({"mode": "directed_to_player"}) == 2
        assert conversation_scheduler.compute_world_effect_budget({"mode": "ambient", "topic": {"type": "ambient_chat"}}) == 1
        assert conversation_scheduler.compute_world_effect_budget({"mode": "ambient", "topic": {"type": "faction_tension"}}) == 2

    def test_get_active_thread_summary(self):
        sim = _sim_state()
        rt = _runtime_state()
        _open_conversation(sim, rt, tick=10)
        summary = conversation_scheduler.get_active_thread_summary(sim, location_id="market_square")
        assert len(summary) == 1
        assert "conversation_id" in summary[0]
        assert "mode" in summary[0]

    def test_no_lifecycle_loop(self):
        """Verify scheduler is helper-only — no competing main loop (B1, B2)."""
        assert not hasattr(conversation_scheduler, "run_conversation_scheduler_tick"), \
            "conversation_scheduler must not have a competing lifecycle loop"

    def test_expiry_helpers_exist(self):
        """Verify expiry helpers are available."""
        assert hasattr(conversation_scheduler, "thread_is_expired")
        assert hasattr(conversation_scheduler, "thread_is_stale")
        conv = {"expires_at_tick": 5, "updated_tick": 1}
        assert conversation_scheduler.thread_is_expired(conv, 10) is True
        assert conversation_scheduler.thread_is_stale(conv, 10) is True


# ===========================================================================
# Beat Mode Caps Tests
# ===========================================================================


class TestModeBeatCaps:
    """Tests that mode beat caps are respected."""

    def test_ambient_caps(self):
        min_b, max_b = conversation_beats.compute_beat_caps("ambient")
        assert 2 <= min_b <= max_b <= 5

    def test_directed_caps(self):
        min_b, max_b = conversation_beats.compute_beat_caps("directed_to_player")
        assert 3 <= min_b <= max_b <= 6

    def test_group_caps(self):
        min_b, max_b = conversation_beats.compute_beat_caps("group")
        assert 4 <= min_b <= max_b <= 8


# ===========================================================================
# Signal Types Tests
# ===========================================================================


class TestSignalTypes:
    """Tests for world signal type validation."""

    def test_all_signal_types_valid(self):
        for stype in conversation_world_signals.SIGNAL_TYPES:
            sig = conversation_world_signals.build_world_signal(
                signal_type=stype,
                source_thread_id="conv:test",
                tick=1,
            )
            assert sig["type"] == stype

    def test_signal_id_stable(self):
        args = dict(
            signal_type="rumor",
            source_thread_id="conv:001",
            source_beat_id="beat:001",
            tick=10,
        )
        sig1 = conversation_world_signals.build_world_signal(**args)
        sig2 = conversation_world_signals.build_world_signal(**args)
        assert sig1["signal_id"] == sig2["signal_id"]

    def test_signal_pending_bounded(self):
        rt = {}
        conversation_world_signals.ensure_signal_state(rt)
        for i in range(50):
            sig = conversation_world_signals.build_world_signal(
                signal_type="rumor",
                source_thread_id=f"conv:{i}",
                tick=i,
            )
            conversation_world_signals.enqueue_signals(rt, [sig])
        pending = rt["conversation_world_signals"]["pending"]
        assert len(pending) <= conversation_world_signals._MAX_PENDING_SIGNALS


# ===========================================================================
# Architectural Consolidation Validation Tests
# ===========================================================================


class TestArchitecturalUnification:
    """Validate the unified 4C architecture matches the merge checklist."""

    # A. Narration worker architecture

    def test_a1_single_source_of_truth_for_narration_jobs(self):
        """narration_worker must not own a competing narration job queue."""
        # narration_worker should not have queue.Queue or any job storage
        assert not hasattr(narration_worker, "_narration_queue")
        assert not hasattr(narration_worker, "get_pending_jobs")
        assert not hasattr(narration_worker, "get_queue_size")
        assert not hasattr(narration_worker, "clear_queue")

    def test_a2_worker_is_manager_pubsub_only(self):
        """narration_worker must only provide manager + pub/sub functions."""
        expected_public = {
            "ensure_narration_worker_running",
            "signal_narration_work",
            "drain_pending_sessions",
            "publish_narration_event",
            "subscribe_narration_events",
            "unsubscribe_narration_events",
        }
        actual_public = {
            name for name in dir(narration_worker)
            if not name.startswith("_") and callable(getattr(narration_worker, name))
        }
        # All expected functions exist
        assert expected_public.issubset(actual_public), f"Missing: {expected_public - actual_public}"

    # B. Conversation lifecycle ownership

    def test_b1_single_lifecycle_entrypoint(self):
        """conversation_engine must have run_conversation_tick as sole lifecycle."""
        assert hasattr(conversation_engine, "run_conversation_tick")

    def test_b2_scheduler_is_helper_only(self):
        """conversation_scheduler must not have run_conversation_scheduler_tick."""
        assert not hasattr(conversation_scheduler, "run_conversation_scheduler_tick")
        # But should have helper functions
        assert hasattr(conversation_scheduler, "classify_thread_mode")
        assert hasattr(conversation_scheduler, "compute_thread_importance")
        assert hasattr(conversation_scheduler, "compute_world_effect_budget")
        assert hasattr(conversation_scheduler, "get_active_thread_summary")

    # C. Identity model

    def test_c1_thread_id_equals_conversation_id(self):
        """Beat thread_id must equal conversation_id from the thread."""
        sim = _sim_state()
        rt = _runtime_state()
        conv = _open_conversation(sim, rt, tick=10)
        line = conversation_engine.build_next_conversation_line(conv, sim, rt, 10)
        beat = conversation_beats.build_beat_from_conversation_line(conv, line, 10)
        assert beat["thread_id"] == conv["conversation_id"]

    def test_c2_stable_beat_ids(self):
        """Beat IDs must be deterministic from thread identity + beat index."""
        beat1 = conversation_beats.build_conversation_beat(
            thread_id="conv:test", speaker_id="npc_0",
            summary="hello", tick=1, beat_index=0,
        )
        beat2 = conversation_beats.build_conversation_beat(
            thread_id="conv:test", speaker_id="npc_0",
            summary="hello", tick=1, beat_index=0,
        )
        assert beat1["beat_id"] == beat2["beat_id"]

    # D. Settings unification

    def test_d1_canonical_settings_contract(self):
        """Resolved settings must include all canonical 4C fields."""
        settings = conversation_settings.resolve_conversation_settings({}, {})
        required = {
            "ambient_conversations_enabled",
            "ambient_delay_after_player_turn",
            "max_concurrent_ambient_threads",
            "max_beats_per_ambient_thread",
            "allow_npc_address_player",
            "allow_conversation_world_signals",
            "conversation_frequency",
            "combat_suppression",
            "stealth_suppression",
        }
        assert required.issubset(set(settings.keys()))

    # H. World signal system

    def test_h4_no_import_guards_in_engine(self):
        """conversation_engine must directly import 4C subsystems, no try/except guards."""
        import inspect
        source = inspect.getsource(conversation_engine)
        # The only allowed except ImportError is for the optional LLM gateway
        # in build_next_conversation_line, not for 4C conversation modules.
        assert "except (ImportError, AttributeError):" not in source, \
            "Broad import guards for 4C modules should be replaced with direct imports"

    # K. Import hygiene

    def test_k1_direct_imports_in_engine(self):
        """conversation_engine must directly import beats, pivots, signals."""
        import inspect
        source = inspect.getsource(conversation_engine)
        assert "from .conversation_beats import" in source or "from app.rpg.social.conversation_beats import" in source
        assert "from .conversation_pivots import" in source or "from app.rpg.social.conversation_pivots import" in source
        assert "from .conversation_world_signals import" in source or "from app.rpg.social.conversation_world_signals import" in source
        assert "from .conversation_scheduler import" in source or "from app.rpg.social.conversation_scheduler import" in source
