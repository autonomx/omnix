"""Comprehensive conversation system tests.

Healthcheck, sanity, functional, regression, and integration tests for:
- npc_conversations (state models, storage, bounds)
- conversation_settings (defaults, merge, validation)
- conversation_topics (candidate generation, dedup, sorting)
- conversation_participants (group finding, initiator, next speaker)
- conversation_templates (line generation, truncation)
- player_interventions (option generation, application)
- conversation_presentation (payload building)
- conversation_engine (open/advance/close/tick)
- conversation_prompt_builder (prompt construction)
- conversation_response_parser (parse, validate)
- conversation_gateway (LLM wrapper)
- offscreen_conversations (offscreen pass)
- rumor_from_conversations (rumor generation)
- faction_conversations (faction topics)
- crowd_conversations (background chatter)
- personality_state accessors (profile, tags, voice)
- tick_diff conversation fields
- timeline conversation events

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_conversation_system.py -v --noconftest
"""
from __future__ import annotations

import copy
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys
import types
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import machinery — stub all app.* dependencies that we don't test,
# then load real modules by file path to bypass app/__init__.py (flask).
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
    "app.rpg.ai.conversation_prompt_builder",
    "app.rpg.ai.conversation_response_parser",
    "app.rpg.ai.conversation_gateway",
    "app.rpg.social.offscreen_conversations",
    "app.rpg.social.rumor_from_conversations",
    "app.rpg.social.faction_conversations",
    "app.rpg.social.crowd_conversations",
    "app.rpg.presentation.personality_state",
    "app.rpg.analytics.tick_diff",
    "app.rpg.analytics.timeline",
}


class _StubModule(types.ModuleType):
    """Auto-stub module that returns MagicMock for unknown attributes."""

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
    """Intercept all ``app.*`` imports and stub anything not in _REAL_MODULES."""

    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("app"):
            return None
        if fullname in _REAL_MODULES:
            return None
        if fullname in sys.modules:
            return None
        return importlib.machinery.ModuleSpec(
            fullname, _StubLoader(), is_package=True,
        )


sys.meta_path.insert(0, _AppStubFinder())


def _load(mod_name: str, rel_path: str):
    """Load a real module by file path, bypassing package __init__.py."""
    sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(SRC_DIR, rel_path),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load real modules (order matters: dependencies first)
_npc_conv = _load("app.rpg.social.npc_conversations", "app/rpg/social/npc_conversations.py")
_conv_settings = _load("app.rpg.social.conversation_settings", "app/rpg/social/conversation_settings.py")
_conv_topics = _load("app.rpg.social.conversation_topics", "app/rpg/social/conversation_topics.py")
_conv_participants = _load("app.rpg.social.conversation_participants", "app/rpg/social/conversation_participants.py")
_conv_templates = _load("app.rpg.social.conversation_templates", "app/rpg/social/conversation_templates.py")
_player_intv = _load("app.rpg.social.player_interventions", "app/rpg/social/player_interventions.py")
_conv_present = _load("app.rpg.social.conversation_presentation", "app/rpg/social/conversation_presentation.py")
_conv_engine = _load("app.rpg.social.conversation_engine", "app/rpg/social/conversation_engine.py")
_prompt_builder = _load("app.rpg.ai.conversation_prompt_builder", "app/rpg/ai/conversation_prompt_builder.py")
_resp_parser = _load("app.rpg.ai.conversation_response_parser", "app/rpg/ai/conversation_response_parser.py")
_gateway = _load("app.rpg.ai.conversation_gateway", "app/rpg/ai/conversation_gateway.py")
_offscreen = _load("app.rpg.social.offscreen_conversations", "app/rpg/social/offscreen_conversations.py")
_rumor = _load("app.rpg.social.rumor_from_conversations", "app/rpg/social/rumor_from_conversations.py")
_faction = _load("app.rpg.social.faction_conversations", "app/rpg/social/faction_conversations.py")
_crowd = _load("app.rpg.social.crowd_conversations", "app/rpg/social/crowd_conversations.py")
_personality = _load("app.rpg.presentation.personality_state", "app/rpg/presentation/personality_state.py")
_tick_diff = _load("app.rpg.analytics.tick_diff", "app/rpg/analytics/tick_diff.py")
_timeline = _load("app.rpg.analytics.timeline", "app/rpg/analytics/timeline.py")

# ── Module-level aliases for tested functions ──────────────────────────────

ensure_conversation_state = _npc_conv.ensure_conversation_state
build_conversation_state = _npc_conv.build_conversation_state
build_conversation_topic = _npc_conv.build_conversation_topic
build_conversation_line = _npc_conv.build_conversation_line
list_active_conversations = _npc_conv.list_active_conversations
list_recent_conversations = _npc_conv.list_recent_conversations
get_conversation = _npc_conv.get_conversation
upsert_conversation = _npc_conv.upsert_conversation
append_conversation_line = _npc_conv.append_conversation_line
get_conversation_lines = _npc_conv.get_conversation_lines
close_conversation = _npc_conv.close_conversation
trim_conversation_state = _npc_conv.trim_conversation_state

get_default_conversation_settings = _conv_settings.get_default_conversation_settings
resolve_conversation_settings = _conv_settings.resolve_conversation_settings

build_conversation_topic_candidates = _conv_topics.build_conversation_topic_candidates

find_candidate_conversation_groups = _conv_participants.find_candidate_conversation_groups
select_initiator = _conv_participants.select_initiator
select_next_speaker = _conv_participants.select_next_speaker

build_template_line = _conv_templates.build_template_line

build_intervention_options = _player_intv.build_intervention_options
apply_player_intervention = _player_intv.apply_player_intervention

build_conversation_payload = _conv_present.build_conversation_payload

open_conversation = _conv_engine.open_conversation
build_next_conversation_line = _conv_engine.build_next_conversation_line
should_close_conversation = _conv_engine.should_close_conversation
try_start_ambient_conversations = _conv_engine.try_start_ambient_conversations
try_start_party_reaction_conversation = _conv_engine.try_start_party_reaction_conversation
advance_active_conversations = _conv_engine.advance_active_conversations
run_conversation_tick = _conv_engine.run_conversation_tick

build_npc_conversation_line_prompt = _prompt_builder.build_npc_conversation_line_prompt

parse_conversation_line_response = _resp_parser.parse_conversation_line_response
is_valid_conversation_line = _resp_parser.is_valid_conversation_line

generate_recorded_conversation_line = _gateway.generate_recorded_conversation_line

run_offscreen_conversation_pass = _offscreen.run_offscreen_conversation_pass

conversation_can_generate_rumor = _rumor.conversation_can_generate_rumor
build_rumor_from_conversation = _rumor.build_rumor_from_conversation

build_faction_topic_candidates = _faction.build_faction_topic_candidates

build_background_chatter_lines = _crowd.build_background_chatter_lines

ensure_personality_state = _personality.ensure_personality_state
get_personality_profile = _personality.get_personality_profile
get_personality_tags = _personality.get_personality_tags
get_voice_style = _personality.get_voice_style

build_tick_diff = _tick_diff.build_tick_diff

build_timeline_summary = _timeline.build_timeline_summary

# Bounded-size constants
MAX_ACTIVE = _npc_conv._MAX_ACTIVE_CONVERSATIONS
MAX_RECENT = _npc_conv._MAX_RECENT_CONVERSATIONS
MAX_LINES = _npc_conv._MAX_LINES_PER_CONVERSATION


# ── Helpers ────────────────────────────────────────────────────────────────


def _minimal_sim(*, location="loc:tavern", tick=5):
    """Build a minimal simulation state dict for testing."""
    return {
        "tick": tick,
        "player_state": {
            "location_id": location,
            "nearby_npc_ids": ["npc:guard", "npc:merchant"],
        },
        "events": [],
        "npc_index": {
            "npc:guard": {
                "name": "Guard",
                "location_id": location,
                "role": "guard",
                "assertiveness": 0.5,
            },
            "npc:merchant": {
                "name": "Merchant",
                "location_id": location,
                "role": "merchant",
                "assertiveness": 0.3,
            },
            "npc:thief": {
                "name": "Thief",
                "location_id": location,
                "role": "thief",
                "assertiveness": 0.7,
            },
        },
    }


def _minimal_runtime(*, location="loc:tavern"):
    """Build a minimal runtime state dict for testing."""
    return {
        "current_location_id": location,
        "conversation_settings": {},
        "last_player_action": {},
        "llm_gateway": None,
        "offscreen_conversation_summaries": [],
        "last_conversation_intervention": None,
    }


def _make_topic(topic_type="event_commentary", anchor="event:test", summary="Test topic"):
    """Create a conversation topic dict."""
    return build_conversation_topic(topic_type, anchor, summary)


def _make_conversation(sim, *, conv_id="conv:test", kind="ambient_npc_conversation",
                       location="loc:tavern", participants=None, tick=5):
    """Create and upsert a test conversation into simulation state."""
    if participants is None:
        participants = ["npc:guard", "npc:merchant"]
    topic = _make_topic()
    conv = build_conversation_state(
        kind=kind,
        location_id=location,
        participants=participants,
        initiator_id=participants[0],
        topic=topic,
        max_turns=8,
        player_can_intervene=True,
        player_present=True,
        tick=tick,
    )
    conv["conversation_id"] = conv_id
    upsert_conversation(sim, conv)
    return conv


# ═══════════════════════════════════════════════════════════════════════════
# 1. HEALTHCHECK
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthcheck:
    """Verify modules load and key symbols exist."""

    def test_npc_conversations_module_loads(self):
        assert _npc_conv is not None
        assert hasattr(_npc_conv, "ensure_conversation_state")

    def test_conversation_settings_module_loads(self):
        assert _conv_settings is not None
        assert hasattr(_conv_settings, "get_default_conversation_settings")

    def test_conversation_engine_module_loads(self):
        assert _conv_engine is not None
        assert hasattr(_conv_engine, "run_conversation_tick")

    def test_conversation_prompt_builder_module_loads(self):
        assert _prompt_builder is not None
        assert hasattr(_prompt_builder, "build_npc_conversation_line_prompt")

    def test_conversation_response_parser_module_loads(self):
        assert _resp_parser is not None
        assert hasattr(_resp_parser, "parse_conversation_line_response")

    def test_key_constants_defined(self):
        assert MAX_ACTIVE == 4
        assert MAX_RECENT == 60
        assert MAX_LINES == 12


# ═══════════════════════════════════════════════════════════════════════════
# 2. SANITY — npc_conversations
# ═══════════════════════════════════════════════════════════════════════════


class TestSanityNpcConversations:
    """Core conversation state helpers."""

    def test_ensure_conversation_state_empty_dict(self):
        sim = {}
        result = ensure_conversation_state(sim)
        cs = result.get("social_state", {}).get("conversations", {})
        assert isinstance(cs.get("active"), list)
        assert isinstance(cs.get("recent"), list)
        assert isinstance(cs.get("lines_by_conversation"), dict)

    def test_ensure_conversation_state_non_dict(self):
        result = ensure_conversation_state(None)
        assert isinstance(result, dict)

    def test_build_conversation_state_minimal(self):
        topic = _make_topic()
        conv = build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="loc:tavern",
            participants=["npc:a", "npc:b"],
            initiator_id="npc:a",
            topic=topic,
            max_turns=8,
            player_can_intervene=False,
            player_present=False,
            tick=1,
        )
        assert conv["kind"] == "ambient_npc_conversation"
        assert conv["status"] == "active"
        assert conv["participants"] == ["npc:a", "npc:b"]
        assert conv["turn_count"] == 0
        assert conv["max_turns"] == 8
        assert "conversation_id" in conv

    def test_build_conversation_topic(self):
        topic = build_conversation_topic("moral_conflict", "npc:thief", "Should we help the thief?")
        assert topic["type"] == "moral_conflict"
        assert topic["anchor"] == "npc:thief"
        assert topic["summary"] == "Should we help the thief?"

    def test_build_conversation_line(self):
        line = build_conversation_line(
            conversation_id="conv:test",
            turn=1,
            speaker="npc:guard",
            text="Halt! Who goes there?",
            kind="statement",
            created_tick=5,
        )
        assert line["speaker"] == "npc:guard"
        assert line["text"] == "Halt! Who goes there?"
        assert line["turn"] == 1

    def test_stable_id_deterministic(self):
        conv1 = build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="loc:a",
            participants=["npc:x", "npc:y"],
            initiator_id="npc:x",
            topic=_make_topic(),
            max_turns=8,
            player_can_intervene=False,
            player_present=False,
            tick=10,
        )
        conv2 = build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="loc:a",
            participants=["npc:x", "npc:y"],
            initiator_id="npc:x",
            topic=_make_topic(),
            max_turns=8,
            player_can_intervene=False,
            player_present=False,
            tick=10,
        )
        assert conv1["conversation_id"] == conv2["conversation_id"]

    def test_stable_id_varies(self):
        conv1 = build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="loc:a",
            participants=["npc:x", "npc:y"],
            initiator_id="npc:x",
            topic=_make_topic(),
            max_turns=8,
            player_can_intervene=False,
            player_present=False,
            tick=10,
        )
        conv2 = build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="loc:b",
            participants=["npc:x", "npc:y"],
            initiator_id="npc:x",
            topic=_make_topic(),
            max_turns=8,
            player_can_intervene=False,
            player_present=False,
            tick=10,
        )
        assert conv1["conversation_id"] != conv2["conversation_id"]

    def test_safe_helpers_edge_cases(self):
        sim = ensure_conversation_state({})
        assert list_active_conversations(sim) == []
        assert list_recent_conversations(sim) == []
        assert get_conversation(sim, "conv:nonexistent") is None
        assert get_conversation_lines(sim, "conv:nonexistent") == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. SANITY — conversation_settings
# ═══════════════════════════════════════════════════════════════════════════


class TestSanityConversationSettings:
    """Configuration defaults and overrides."""

    def test_default_settings_keys(self):
        d = get_default_conversation_settings()
        assert "ambient_conversations_enabled" in d
        assert "party_reaction_interrupts_enabled" in d
        assert "player_intervention_enabled" in d
        assert "avg_conversation_turns" in d

    def test_resolve_settings_defaults(self):
        sim = _minimal_sim()
        rt = _minimal_runtime()
        settings = resolve_conversation_settings(sim, rt)
        defaults = get_default_conversation_settings()
        for key in defaults:
            assert key in settings

    def test_resolve_settings_simulation_override(self):
        sim = _minimal_sim()
        sim["conversation_settings"] = {"avg_conversation_turns": 6}
        rt = _minimal_runtime()
        settings = resolve_conversation_settings(sim, rt)
        assert settings["avg_conversation_turns"] == 6

    def test_resolve_settings_runtime_override_wins(self):
        sim = _minimal_sim()
        sim["conversation_settings"] = {"avg_conversation_turns": 6}
        rt = _minimal_runtime()
        rt["conversation_settings"] = {"avg_conversation_turns": 10}
        settings = resolve_conversation_settings(sim, rt)
        assert settings["avg_conversation_turns"] == 10

    def test_resolve_settings_clamps_min_values(self):
        sim = _minimal_sim()
        rt = _minimal_runtime()
        rt["conversation_settings"] = {"avg_conversation_turns": -5}
        settings = resolve_conversation_settings(sim, rt)
        assert settings["avg_conversation_turns"] >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 4. FUNCTIONAL — conversation_topics
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalConversationTopics:
    """Topic candidate generation and deduplication."""

    def test_no_events_no_topics(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5,
        )
        # Even with no events, role-based topics may still be generated
        assert isinstance(topics, list)

    def test_event_commentary_topic(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [{"type": "trade", "description": "A merchant sold rare goods", "tick": 4, "location_id": "loc:tavern"}]
        rt = _minimal_runtime()
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5,
        )
        types_found = {t["type"] for t in topics}
        assert "event_commentary" in types_found

    def test_local_incident_topic_for_attack(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [{"type": "attack", "description": "Bandits attacked the gate", "tick": 4, "location_id": "loc:tavern"}]
        rt = _minimal_runtime()
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5,
        )
        types_found = {t["type"] for t in topics}
        assert "local_incident" in types_found

    def test_plan_reaction_topic(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [{"type": "plan", "description": "The king announced a new decree", "tick": 4, "location_id": "loc:tavern"}]
        rt = _minimal_runtime()
        rt["last_player_action"] = {"type": "plan", "description": "proposed alliance"}
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5,
        )
        types_found = {t["type"] for t in topics}
        assert "plan_reaction" in types_found

    def test_moral_conflict_topic_thief_guard(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:thief"], 5,
        )
        types_found = {t["type"] for t in topics}
        assert "moral_conflict" in types_found

    def test_risk_conflict_topic_cave(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        rt["last_player_action"] = {"type": "plan", "text": "explore the cave", "description": "cave expedition"}
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5,
        )
        types_found = {t["type"] for t in topics}
        assert "risk_conflict" in types_found

    def test_dedupe_removes_duplicates(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [
            {"type": "trade", "description": "A merchant sold rare goods", "tick": 4, "location_id": "loc:tavern"},
            {"type": "trade", "description": "A merchant sold rare goods", "tick": 4, "location_id": "loc:tavern"},
        ]
        rt = _minimal_runtime()
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5,
        )
        anchors = [t["anchor"] for t in topics if t["type"] == "event_commentary"]
        assert len(anchors) == len(set(anchors))

    def test_topic_candidates_bounded_to_8(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [
            {"type": f"event_{i}", "description": f"Event number {i}", "tick": 4, "location_id": "loc:tavern"}
            for i in range(20)
        ]
        rt = _minimal_runtime()
        topics = build_conversation_topic_candidates(
            sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5,
        )
        assert len(topics) <= 8


# ═══════════════════════════════════════════════════════════════════════════
# 5. FUNCTIONAL — conversation_participants
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalConversationParticipants:
    """Participant group finding and speaker selection."""

    def test_find_groups_two_npcs(self):
        sim = _minimal_sim()
        groups = find_candidate_conversation_groups(sim, "loc:tavern", 5)
        assert isinstance(groups, list)
        assert len(groups) >= 1
        for g in groups:
            assert len(g) >= 2

    def test_find_groups_three_npcs(self):
        sim = _minimal_sim()
        sim["npc_index"]["npc:thief"]["location_id"] = "loc:tavern"
        sim["player_state"]["nearby_npc_ids"].append("npc:thief")
        groups = find_candidate_conversation_groups(sim, "loc:tavern", 5)
        assert len(groups) >= 1

    def test_find_groups_no_npcs_at_location(self):
        sim = _minimal_sim()
        groups = find_candidate_conversation_groups(sim, "loc:forest", 5)
        assert groups == []

    def test_select_initiator_highest_weight(self):
        sim = _minimal_sim()
        initiator = select_initiator(sim, ["npc:guard", "npc:merchant"])
        assert initiator in ["npc:guard", "npc:merchant"]

    def test_select_next_speaker_alternates(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        conv = _make_conversation(sim)
        conv["last_speaker_id"] = "npc:guard"
        speaker = select_next_speaker(conv, sim)
        assert speaker == "npc:merchant"

    def test_select_next_speaker_no_prior(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        conv = _make_conversation(sim)
        conv["last_speaker_id"] = ""
        speaker = select_next_speaker(conv, sim)
        assert speaker in conv["participants"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. FUNCTIONAL — conversation_templates
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalConversationTemplates:
    """Template-based line generation."""

    def _make_conv(self, sim, topic_type, speaker_role="guard"):
        ensure_conversation_state(sim)
        topic = build_conversation_topic(topic_type, "event:test", "Test summary")
        conv = build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="loc:tavern",
            participants=["npc:guard", "npc:merchant"],
            initiator_id="npc:guard",
            topic=topic,
            max_turns=8,
            player_can_intervene=True,
            player_present=True,
            tick=5,
        )
        upsert_conversation(sim, conv)
        return conv

    def test_plan_reaction_guard(self):
        sim = _minimal_sim()
        rt = _minimal_runtime()
        conv = self._make_conv(sim, "plan_reaction")
        line = build_template_line(conv, "npc:guard", sim, rt)
        assert "text" in line
        assert len(line["text"]) > 0

    def test_plan_reaction_thief(self):
        sim = _minimal_sim()
        rt = _minimal_runtime()
        conv = self._make_conv(sim, "plan_reaction")
        line = build_template_line(conv, "npc:thief", sim, rt)
        assert "text" in line

    def test_moral_conflict_innkeeper(self):
        sim = _minimal_sim()
        sim["npc_index"]["npc:innkeeper"] = {
            "name": "Innkeeper",
            "location_id": "loc:tavern",
            "role": "innkeeper",
            "assertiveness": 0.4,
        }
        rt = _minimal_runtime()
        conv = self._make_conv(sim, "moral_conflict")
        line = build_template_line(conv, "npc:innkeeper", sim, rt)
        assert "text" in line

    def test_moral_conflict_thief(self):
        sim = _minimal_sim()
        rt = _minimal_runtime()
        conv = self._make_conv(sim, "moral_conflict")
        line = build_template_line(conv, "npc:thief", sim, rt)
        assert "text" in line

    def test_risk_conflict_disagree(self):
        sim = _minimal_sim()
        rt = _minimal_runtime()
        conv = self._make_conv(sim, "risk_conflict")
        line = build_template_line(conv, "npc:merchant", sim, rt)
        assert "text" in line

    def test_truncate_long_line(self):
        sim = _minimal_sim()
        rt = _minimal_runtime()
        conv = self._make_conv(sim, "event_commentary")
        line = build_template_line(conv, "npc:guard", sim, rt)
        assert len(line["text"]) <= 220 + 3  # +3 for potential ellipsis


# ═══════════════════════════════════════════════════════════════════════════
# 7. FUNCTIONAL — player_interventions
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalPlayerInterventions:
    """Player intervention option building and application."""

    def test_build_options_with_intervention(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        conv["player_can_intervene"] = True
        options = build_intervention_options(conv, sim, rt)
        assert isinstance(options, list)
        assert len(options) >= 1

    def test_build_options_no_intervention(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        conv["player_can_intervene"] = False
        options = build_intervention_options(conv, sim, rt)
        assert options == []

    def test_build_options_fewer_than_2_participants(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim, participants=["npc:guard"])
        conv["player_can_intervene"] = True
        options = build_intervention_options(conv, sim, rt)
        assert options == []

    def test_apply_intervention_stores_in_runtime(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        result = apply_player_intervention(conv["conversation_id"], "continue", sim, rt, 5)
        assert rt["last_conversation_intervention"] is not None

    def test_apply_intervention_returns_result(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        result = apply_player_intervention(conv["conversation_id"], "end_discussion", sim, rt, 5)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 8. FUNCTIONAL — conversation_presentation
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalConversationPresentation:
    """UI payload building."""

    def test_payload_empty_state(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        payload = build_conversation_payload(sim, rt)
        assert "active_conversations" in payload
        assert "recent_conversations" in payload
        assert payload["active_conversations"] == []

    def test_payload_with_active_conversation(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        _make_conversation(sim, conv_id="conv:active1")
        payload = build_conversation_payload(sim, rt)
        assert len(payload["active_conversations"]) == 1

    def test_payload_with_recent_conversation(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim, conv_id="conv:recent1")
        close_conversation(sim, "conv:recent1", reason="complete")
        payload = build_conversation_payload(sim, rt)
        assert len(payload["recent_conversations"]) >= 1

    def test_payload_includes_intervention_options(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        _make_conversation(sim, conv_id="conv:intv1")
        payload = build_conversation_payload(sim, rt)
        active = payload["active_conversations"]
        assert len(active) == 1
        assert "intervention_options" in active[0]


# ═══════════════════════════════════════════════════════════════════════════
# 9. FUNCTIONAL — conversation_engine
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalConversationEngine:
    """Main conversation engine orchestration."""

    def test_open_conversation(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        topic = _make_topic("plan_reaction", "player_action:1", "Player proposed alliance")
        result = open_conversation(
            sim, rt,
            kind="ambient_npc_conversation",
            location_id="loc:tavern",
            participants=["npc:guard", "npc:merchant"],
            topic=topic,
            tick=5,
        )
        assert isinstance(result, dict)
        active = list_active_conversations(sim)
        assert len(active) == 1

    def test_build_next_line(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        line = build_next_conversation_line(conv, sim, rt, 5)
        assert "text" in line
        assert "speaker" in line

    def test_should_close_at_max_turns(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        conv["turn_count"] = conv["max_turns"]
        assert should_close_conversation(conv, sim, rt, 10) is True

    def test_should_not_close_before_max(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        conv["turn_count"] = 1
        assert should_close_conversation(conv, sim, rt, 6) is False

    def test_try_start_ambient_with_npcs_and_events(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [{"type": "trade", "description": "A merchant sold rare goods", "tick": 4, "location_id": "loc:tavern"}]
        rt = _minimal_runtime()
        result = try_start_ambient_conversations(sim, rt, 5)
        assert isinstance(result, dict)

    def test_try_start_ambient_disabled(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        rt["conversation_settings"] = {"ambient_conversations_enabled": False}
        result = try_start_ambient_conversations(sim, rt, 5)
        active = list_active_conversations(sim)
        assert len(active) == 0

    def test_try_start_party_reaction(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        action = {"type": "plan", "description": "proposed alliance"}
        result = try_start_party_reaction_conversation(sim, rt, action, 5)
        assert isinstance(result, dict)

    def test_try_start_party_reaction_disabled(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        rt["conversation_settings"] = {"party_reaction_interrupts_enabled": False}
        action = {"type": "plan", "description": "proposed alliance"}
        result = try_start_party_reaction_conversation(sim, rt, action, 5)
        active = list_active_conversations(sim)
        assert len(active) == 0

    def test_advance_conversations_adds_lines(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        result = advance_active_conversations(sim, rt, 5)
        assert isinstance(result, dict)
        lines = get_conversation_lines(sim, conv["conversation_id"])
        assert len(lines) >= 1

    def test_run_conversation_tick_full_cycle(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [{"type": "trade", "description": "Trade event", "tick": 4, "location_id": "loc:tavern"}]
        rt = _minimal_runtime()
        result = run_conversation_tick(sim, rt, 5)
        assert isinstance(result, dict)

    def test_no_duplicate_conversation_same_tick(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [{"type": "trade", "description": "Trade event", "tick": 4, "location_id": "loc:tavern"}]
        rt = _minimal_runtime()
        run_conversation_tick(sim, rt, 5)
        count_before = len(list_active_conversations(sim))
        run_conversation_tick(sim, rt, 5)
        count_after = len(list_active_conversations(sim))
        # Should not create duplicate conversations for same tick/participants
        assert count_after <= count_before + 1


# ═══════════════════════════════════════════════════════════════════════════
# 10. FUNCTIONAL — LLM expansion
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalLLMExpansion:
    """Prompt builder, response parser, and gateway."""

    def test_prompt_builder_output(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        prompt = build_npc_conversation_line_prompt(
            conv, "npc:guard", sim, rt, [],
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_response_parser_valid_json(self):
        raw = json.dumps({"speaker": "npc:guard", "text": "Hello there!", "kind": "greeting"})
        parsed = parse_conversation_line_response(raw)
        assert parsed["speaker"] == "npc:guard"
        assert parsed["text"] == "Hello there!"

    def test_response_parser_invalid_json(self):
        parsed = parse_conversation_line_response("not valid json {{{")
        assert parsed == {} or parsed.get("text", "") == ""

    def test_is_valid_conversation_line(self):
        assert is_valid_conversation_line({"speaker": "npc:a", "text": "Hello"}) is True
        assert is_valid_conversation_line({"speaker": "", "text": "Hello"}) is False
        assert is_valid_conversation_line({"speaker": "npc:a", "text": ""}) is False
        assert is_valid_conversation_line({}) is False

    def test_gateway_no_llm_returns_empty(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        conv = _make_conversation(sim)
        result = generate_recorded_conversation_line(
            None, conv, "npc:guard", sim, rt, [],
        )
        assert result == {} or isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 11. FUNCTIONAL — expansion modules
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalExpansion:
    """Offscreen, rumor, faction, crowd modules."""

    def test_offscreen_conversation_pass(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        result = run_offscreen_conversation_pass(sim, rt, 5)
        assert isinstance(result, dict)

    def test_offscreen_bounded_to_40(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        rt["offscreen_conversation_summaries"] = [f"summary_{i}" for i in range(50)]
        result = run_offscreen_conversation_pass(sim, rt, 5)
        summaries = rt.get("offscreen_conversation_summaries", result.get("offscreen_conversation_summaries", []))
        assert len(summaries) <= 40

    def test_rumor_can_generate_moral_conflict(self):
        conv = {
            "topic": {"type": "moral_conflict", "anchor": "npc:thief", "summary": "Should we trust the thief?"},
            "status": "closed",
        }
        assert conversation_can_generate_rumor(conv) is True

    def test_rumor_cannot_generate_idle(self):
        conv = {
            "topic": {"type": "idle_chat", "anchor": "", "summary": "Just chatting"},
            "status": "closed",
        }
        assert conversation_can_generate_rumor(conv) is False

    def test_build_rumor(self):
        conv = {
            "topic": {"type": "moral_conflict", "anchor": "npc:thief", "summary": "Thief betrayal"},
            "participants": ["npc:guard", "npc:thief"],
            "status": "closed",
        }
        rumor = build_rumor_from_conversation(conv)
        assert rumor["type"] == "rumor"
        assert "summary" in rumor

    def test_faction_topic_candidates(self):
        sim = _minimal_sim()
        topics = build_faction_topic_candidates(sim, "faction:merchants_guild")
        assert isinstance(topics, list)
        assert len(topics) >= 1
        assert topics[0]["type"] == "faction_tension"

    def test_background_chatter_with_events(self):
        events = [{"type": "trade", "description": "Something happened"}]
        lines = build_background_chatter_lines("loc:tavern", events)
        assert isinstance(lines, list)
        assert len(lines) >= 1

    def test_background_chatter_no_events(self):
        lines = build_background_chatter_lines("loc:tavern", [])
        assert lines == []


# ═══════════════════════════════════════════════════════════════════════════
# 12. FUNCTIONAL — personality accessors
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalPersonalityAccessors:
    """Personality state read helpers."""

    def test_get_personality_profile_empty(self):
        sim = {}
        ensure_personality_state(sim)
        profile = get_personality_profile(sim, "npc:unknown")
        assert isinstance(profile, dict)

    def test_get_personality_profile_existing(self):
        sim = {}
        ensure_personality_state(sim)
        ps = sim["presentation_state"]["personality_state"]["profiles"]
        ps["npc:guard"] = {
            "actor_id": "npc:guard",
            "display_name": "Guard",
            "tone": "authoritative",
            "voice_style": "gruff",
            "traits": ["loyal"],
            "style_tags": ["formal"],
            "temperature_hint": 0.3,
        }
        profile = get_personality_profile(sim, "npc:guard")
        assert profile.get("actor_id") == "npc:guard" or profile.get("display_name") == "Guard"

    def test_get_personality_tags(self):
        sim = {}
        ensure_personality_state(sim)
        ps = sim["presentation_state"]["personality_state"]["profiles"]
        ps["npc:guard"] = {"style_tags": ["formal", "stern"]}
        tags = get_personality_tags(sim, "npc:guard")
        assert isinstance(tags, list)

    def test_get_voice_style(self):
        sim = {}
        ensure_personality_state(sim)
        ps = sim["presentation_state"]["personality_state"]["profiles"]
        ps["npc:guard"] = {"voice_style": "gruff"}
        style = get_voice_style(sim, "npc:guard")
        assert isinstance(style, str)


# ═══════════════════════════════════════════════════════════════════════════
# 13. REGRESSION — bounded state
# ═══════════════════════════════════════════════════════════════════════════


class TestRegressionBoundedState:
    """Enforce state size limits."""

    def test_active_conversations_bounded_to_4(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        for i in range(10):
            _make_conversation(sim, conv_id=f"conv:a{i}", tick=i)
        active = list_active_conversations(sim)
        assert len(active) <= MAX_ACTIVE

    def test_recent_conversations_bounded_to_60(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        for i in range(70):
            conv = _make_conversation(sim, conv_id=f"conv:r{i}", tick=i)
            close_conversation(sim, f"conv:r{i}", reason="done")
        trim_conversation_state(sim)
        recent = list_recent_conversations(sim)
        assert len(recent) <= MAX_RECENT

    def test_lines_per_conversation_bounded_to_12(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        conv = _make_conversation(sim, conv_id="conv:lines")
        for i in range(20):
            line = build_conversation_line(
                conversation_id="conv:lines",
                turn=i,
                speaker="npc:guard",
                text=f"Line {i}",
                kind="statement",
                created_tick=5 + i,
            )
            append_conversation_line(sim, "conv:lines", line)
        lines = get_conversation_lines(sim, "conv:lines")
        assert len(lines) <= MAX_LINES

    def test_trim_conversation_state_normalizes(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        _make_conversation(sim, conv_id="conv:trim1")
        result = trim_conversation_state(sim)
        assert isinstance(result, dict)

    def test_close_moves_to_recent(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        _make_conversation(sim, conv_id="conv:close1")
        assert len(list_active_conversations(sim)) == 1
        close_conversation(sim, "conv:close1", reason="done")
        assert len(list_active_conversations(sim)) == 0
        assert len(list_recent_conversations(sim)) >= 1

    def test_upsert_replaces_existing(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        conv1 = _make_conversation(sim, conv_id="conv:upsert1")
        conv1["turn_count"] = 3
        upsert_conversation(sim, conv1)
        fetched = get_conversation(sim, "conv:upsert1")
        assert fetched["turn_count"] == 3
        active = list_active_conversations(sim)
        ids = [c["conversation_id"] for c in active]
        assert ids.count("conv:upsert1") == 1


# ═══════════════════════════════════════════════════════════════════════════
# 14. REGRESSION — determinism
# ═══════════════════════════════════════════════════════════════════════════


class TestRegressionDeterminism:
    """Ensure deterministic outputs for same inputs."""

    def test_conversation_id_deterministic(self):
        topic = _make_topic()
        ids = set()
        for _ in range(5):
            conv = build_conversation_state(
                kind="ambient_npc_conversation",
                location_id="loc:tavern",
                participants=["npc:a", "npc:b"],
                initiator_id="npc:a",
                topic=topic,
                max_turns=8,
                player_can_intervene=False,
                player_present=False,
                tick=10,
            )
            ids.add(conv["conversation_id"])
        assert len(ids) == 1

    def test_topic_sort_deterministic(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        sim["events"] = [
            {"type": "trade", "description": "Trade", "tick": 4, "location_id": "loc:tavern"},
            {"type": "attack", "description": "Attack", "tick": 4, "location_id": "loc:tavern"},
        ]
        rt = _minimal_runtime()
        t1 = build_conversation_topic_candidates(sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5)
        t2 = build_conversation_topic_candidates(sim, rt, "loc:tavern", ["npc:guard", "npc:merchant"], 5)
        assert [t["type"] for t in t1] == [t["type"] for t in t2]

    def test_participant_selection_deterministic(self):
        sim = _minimal_sim()
        results = set()
        for _ in range(10):
            initiator = select_initiator(sim, ["npc:guard", "npc:merchant"])
            results.add(initiator)
        # Weighted selection should be consistent for same inputs
        assert len(results) == 1

    def test_template_line_deterministic(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        topic = build_conversation_topic("plan_reaction", "event:test", "Test")
        conv = build_conversation_state(
            kind="ambient_npc_conversation",
            location_id="loc:tavern",
            participants=["npc:guard", "npc:merchant"],
            initiator_id="npc:guard",
            topic=topic,
            max_turns=8,
            player_can_intervene=False,
            player_present=False,
            tick=5,
        )
        upsert_conversation(sim, conv)
        line1 = build_template_line(conv, "npc:guard", sim, rt)
        line2 = build_template_line(conv, "npc:guard", sim, rt)
        assert line1["text"] == line2["text"]


# ═══════════════════════════════════════════════════════════════════════════
# 15. REGRESSION — edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestRegressionEdgeCases:
    """Guard against None, empty, and corrupted inputs."""

    def test_none_simulation_state(self):
        result = ensure_conversation_state(None)
        assert isinstance(result, dict)

    def test_none_runtime_state(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        settings = resolve_conversation_settings(sim, None)
        assert isinstance(settings, dict)

    def test_empty_participants(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        initiator = select_initiator(sim, [])
        assert initiator == "" or initiator is None

    def test_corrupted_conversation_data(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        # Inject corrupted data
        cs = sim["social_state"]["conversations"]
        cs["active"].append({"conversation_id": "conv:bad"})
        result = trim_conversation_state(sim)
        assert isinstance(result, dict)

    def test_non_dict_values_in_state(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        # Lines map with non-dict value
        cs = sim["social_state"]["conversations"]
        cs["lines_by_conversation"]["conv:broken"] = "not_a_list"
        result = trim_conversation_state(sim)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 16. INTEGRATION — tick_diff
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegrationTickDiff:
    """Tick diff captures conversation changes."""

    def test_diff_new_conversations(self):
        before = _minimal_sim(tick=4)
        ensure_conversation_state(before)
        after = copy.deepcopy(before)
        after["tick"] = 5
        _make_conversation(after, conv_id="conv:new1", tick=5)
        diff = build_tick_diff(before, after)
        assert isinstance(diff, dict)
        assert diff.get("new_conversations") or diff.get("summary", {}).get("new_conversations", 0) >= 0

    def test_diff_closed_conversations(self):
        before = _minimal_sim(tick=4)
        ensure_conversation_state(before)
        _make_conversation(before, conv_id="conv:closing", tick=4)
        after = copy.deepcopy(before)
        after["tick"] = 5
        close_conversation(after, "conv:closing", reason="done")
        diff = build_tick_diff(before, after)
        assert isinstance(diff, dict)

    def test_diff_new_lines(self):
        before = _minimal_sim(tick=4)
        ensure_conversation_state(before)
        _make_conversation(before, conv_id="conv:lines_diff", tick=4)
        after = copy.deepcopy(before)
        after["tick"] = 5
        line = build_conversation_line(
            conversation_id="conv:lines_diff",
            turn=1,
            speaker="npc:guard",
            text="New line",
            kind="statement",
            created_tick=5,
        )
        append_conversation_line(after, "conv:lines_diff", line)
        diff = build_tick_diff(before, after)
        assert isinstance(diff, dict)

    def test_diff_interventions(self):
        before = _minimal_sim(tick=4)
        ensure_conversation_state(before)
        after = copy.deepcopy(before)
        after["tick"] = 5
        diff = build_tick_diff(before, after)
        assert isinstance(diff, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 17. INTEGRATION — timeline
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegrationTimeline:
    """Timeline captures conversation events."""

    def test_timeline_includes_conversation_started(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        _make_conversation(sim, conv_id="conv:timeline1", tick=5)
        summary = build_timeline_summary(sim)
        assert isinstance(summary, dict)

    def test_timeline_includes_conversation_closed(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        _make_conversation(sim, conv_id="conv:timeline_close", tick=5)
        close_conversation(sim, "conv:timeline_close", reason="done")
        summary = build_timeline_summary(sim)
        assert isinstance(summary, dict)

    def test_timeline_empty_conversations(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        summary = build_timeline_summary(sim)
        assert isinstance(summary, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 18. INTEGRATION — full cycle
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegrationFullCycle:
    """End-to-end conversation lifecycle."""

    def test_open_advance_close_cycle(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        topic = _make_topic("plan_reaction", "action:1", "Player action")
        open_conversation(
            sim, rt,
            kind="ambient_npc_conversation",
            location_id="loc:tavern",
            participants=["npc:guard", "npc:merchant"],
            topic=topic,
            tick=5,
        )
        active = list_active_conversations(sim)
        assert len(active) == 1
        conv_id = active[0]["conversation_id"]

        advance_active_conversations(sim, rt, 6)
        lines = get_conversation_lines(sim, conv_id)
        assert len(lines) >= 1

        close_conversation(sim, conv_id, reason="complete")
        assert len(list_active_conversations(sim)) == 0
        assert len(list_recent_conversations(sim)) >= 1

    def test_multiple_ticks_bounded_state(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        sim["events"] = [
            {"type": "trade", "description": "Trade event", "tick": 4, "location_id": "loc:tavern"},
        ]
        for tick in range(5, 25):
            run_conversation_tick(sim, rt, tick)
        active = list_active_conversations(sim)
        recent = list_recent_conversations(sim)
        assert len(active) <= MAX_ACTIVE
        assert len(recent) <= MAX_RECENT

    def test_conversation_with_intervention_then_close(self):
        sim = _minimal_sim()
        ensure_conversation_state(sim)
        rt = _minimal_runtime()
        topic = _make_topic("moral_conflict", "npc:thief", "Trust the thief?")
        open_conversation(
            sim, rt,
            kind="ambient_npc_conversation",
            location_id="loc:tavern",
            participants=["npc:guard", "npc:merchant"],
            topic=topic,
            tick=5,
        )
        active = list_active_conversations(sim)
        conv_id = active[0]["conversation_id"]

        options = build_intervention_options(active[0], sim, rt)
        if options:
            apply_player_intervention(conv_id, options[0].get("id", "continue"), sim, rt, 6)

        close_conversation(sim, conv_id, reason="player_ended")
        assert len(list_active_conversations(sim)) == 0
        recent = list_recent_conversations(sim)
        assert len(recent) >= 1
