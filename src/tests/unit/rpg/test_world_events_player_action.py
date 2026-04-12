"""Tests — World events reflect player activities.

Validates that:
1. The semantic state change LLM prompt includes player action context.
2. World event rows prioritize player-action-related events.
3. Generic NPC beats are deprioritized when a player action is active.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_world_events_player_action.py -v --noconftest
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys
import types
from unittest.mock import MagicMock

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, SRC_DIR)

_REAL_MODULES = {
    "app.rpg.session.runtime",
    "app.rpg.analytics.world_events",
    "app.rpg.creator.schema",
    "app.rpg.creator.defaults",
    "app.rpg.creator.validation",
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
        if fullname in sys.modules:
            return None
        return importlib.machinery.ModuleSpec(
            fullname, _StubLoader(), is_package=True,
        )


sys.meta_path.insert(0, _AppStubFinder())


def _load(mod_name: str, rel_path: str):
    sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(SRC_DIR, rel_path),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_schema = _load("app.rpg.creator.schema", "app/rpg/creator/schema.py")
_defaults = _load("app.rpg.creator.defaults", "app/rpg/creator/defaults.py")
_validation = _load("app.rpg.creator.validation", "app/rpg/creator/validation.py")
_rt = _load("app.rpg.session.runtime", "app/rpg/session/runtime.py")
_we = _load("app.rpg.analytics.world_events", "app/rpg/analytics/world_events.py")

_build_semantic_state_change_prompt_contract = _rt._build_semantic_state_change_prompt_contract
build_incremental_world_event_rows = _we.build_incremental_world_event_rows
build_player_world_view_rows = _we.build_player_world_view_rows
build_player_local_world_view_rows = _we.build_player_local_world_view_rows
_player_bias = _we._player_bias
_row_sort_key = _we._row_sort_key


def _sim(tick=10, **overrides):
    state = {
        "tick": tick,
        "scene_title": "Tavern Scene",
        "location_name": "The Rusty Sword",
        "player_state": {"location_id": "loc_tavern"},
        "locations": [{"id": "loc_tavern", "name": "Tavern"}],
        "events": [],
        "incidents": [],
        "sandbox_state": {},
        "threads": [],
        "actor_states": [
            {"id": "npc_innkeeper", "name": "Bran", "activity": "tending_bar", "availability": "", "location_id": "loc_tavern", "mood": "", "intent": "", "engagement": ""},
            {"id": "npc_guard_captain", "name": "Captain Aldric", "activity": "patrolling", "availability": "", "location_id": "loc_tavern", "mood": "", "intent": "", "engagement": "alert"},
        ],
        "active_interactions": [],
        "npc_index": {
            "npc_innkeeper": {"id": "npc_innkeeper", "name": "Bran", "location_id": "loc_tavern"},
            "npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"},
        },
    }
    state.update(overrides)
    return state


def _rt_state(**overrides):
    state = {
        "tick": 10,
        "ambient_queue": [],
        "recent_world_event_rows": [],
        "recent_scene_beats": [],
        "accepted_state_change_events": [],
        "opening_runtime": {"active": False},
        "last_player_action": {},
    }
    state.update(overrides)
    return state


# ── Semantic LLM prompt includes player action context ──────────────────────

class TestPromptIncludesPlayerAction:
    def test_prompt_includes_recent_player_action_when_present(self):
        sim = _sim()
        rt = _rt_state(last_player_action={
            "action_id": "player_action:11",
            "action_type": "social_competition",
            "text": "I arm wrestle Bran",
            "target_id": "npc_innkeeper",
        })
        prompt = _build_semantic_state_change_prompt_contract(sim, rt)
        assert "recent_player_action" in prompt
        assert "arm wrestle" in prompt.lower()
        assert "REACT TO PLAYER ACTION" in prompt

    def test_prompt_omits_player_action_when_empty(self):
        sim = _sim()
        rt = _rt_state(last_player_action={})
        prompt = _build_semantic_state_change_prompt_contract(sim, rt)
        assert "recent_player_action" not in prompt
        assert "REACT TO PLAYER ACTION" not in prompt

    def test_prompt_includes_recent_scene_beats(self):
        sim = _sim()
        rt = _rt_state(
            last_player_action={"text": "I challenge Bran", "action_type": "social_competition", "target_id": "npc_innkeeper"},
            recent_scene_beats=[
                {"beat_id": "b1", "tick": 10, "kind": "interaction_beat", "summary": "Player challenges Bran to arm wrestling."},
            ],
        )
        prompt = _build_semantic_state_change_prompt_contract(sim, rt)
        assert "recent_scene_beats" in prompt
        assert "arm wrestling" in prompt.lower()

    def test_prompt_still_valid_json_in_input_section(self):
        sim = _sim()
        rt = _rt_state(last_player_action={
            "action_id": "player_action:11",
            "action_type": "social_competition",
            "text": "I arm wrestle Bran",
            "target_id": "npc_innkeeper",
        })
        prompt = _build_semantic_state_change_prompt_contract(sim, rt)
        # Extract JSON from INPUT section
        input_marker = "INPUT:\n"
        idx = prompt.index(input_marker)
        json_str = prompt[idx + len(input_marker):]
        payload = json.loads(json_str)
        assert "recent_player_action" in payload
        assert payload["recent_player_action"]["action_type"] == "social_competition"

    def test_prompt_player_action_text_truncated(self):
        sim = _sim()
        long_text = "x" * 500
        rt = _rt_state(last_player_action={
            "text": long_text,
            "action_type": "observe",
            "target_id": "",
        })
        prompt = _build_semantic_state_change_prompt_contract(sim, rt)
        input_marker = "INPUT:\n"
        idx = prompt.index(input_marker)
        payload = json.loads(prompt[idx + len(input_marker):])
        assert len(payload["recent_player_action"]["text"]) <= 200


# ── Player bias in row sorting ──────────────────────────────────────────────

class TestPlayerBias:
    def test_player_action_tag_gives_bias(self):
        row = {"tags": ["player_action"], "source": "test", "kind": "activity_beat"}
        assert _player_bias(row) == 1

    def test_player_engaged_tag_gives_bias(self):
        row = {"tags": ["player_engaged"], "source": "test", "kind": "activity_beat"}
        assert _player_bias(row) == 1

    def test_interaction_beat_kind_gives_bias(self):
        row = {"tags": [], "source": "test", "kind": "interaction_beat"}
        assert _player_bias(row) == 1

    def test_world_pressure_kind_gives_bias(self):
        row = {"tags": [], "source": "test", "kind": "world_pressure"}
        assert _player_bias(row) == 1

    def test_world_rumor_kind_gives_bias(self):
        row = {"tags": [], "source": "test", "kind": "world_rumor"}
        assert _player_bias(row) == 1

    def test_generic_npc_beat_has_no_bias(self):
        row = {"tags": [], "source": "activity_runtime", "kind": "activity_beat"}
        assert _player_bias(row) == 0

    def test_player_biased_rows_sort_before_generic(self):
        player_row = {"event_id": "p1", "scope": "local", "tags": ["player_action"], "source": "test", "kind": "interaction_beat", "priority": 0.5, "tick": 10}
        generic_row = {"event_id": "g1", "scope": "local", "tags": [], "source": "activity_runtime", "kind": "activity_beat", "priority": 0.8, "tick": 10}
        rows = [generic_row, player_row]
        rows.sort(key=_row_sort_key)
        assert rows[0]["event_id"] == "p1"


# ── Incremental world events prioritize player actions ──────────────────────

class TestIncrementalPlayerActionPriority:
    def test_player_action_events_surface_over_generic_beats(self):
        sim = _sim(tick=50)
        rt = _rt_state(
            tick=50,
            last_player_action={"text": "arm wrestle", "action_type": "social_competition", "target_id": "npc_innkeeper"},
            recent_scene_beats=[
                {"beat_id": "player_beat:1", "tick": 50, "kind": "interaction_beat", "summary": "Player arm wrestles Bran.", "tags": ["player_action"], "location_id": "loc_tavern"},
                {"beat_id": "generic_1", "tick": 50, "kind": "activity_beat", "summary": "Captain Aldric scans the tavern.", "tags": [], "actor_id": "npc_guard_captain", "location_id": "loc_tavern"},
                {"beat_id": "generic_2", "tick": 50, "kind": "activity_beat", "summary": "Elara serves drinks.", "tags": [], "actor_id": "npc_merchant", "location_id": "loc_tavern"},
            ],
        )
        rows = build_incremental_world_event_rows(sim, rt, {})
        assert len(rows) >= 1
        # Player beat should be first
        assert "arm wrestle" in rows[0]["summary"].lower() or rows[0]["kind"] == "interaction_beat"

    def test_player_consequence_events_surface(self):
        sim = _sim(tick=50)
        rt = _rt_state(
            tick=50,
            last_player_action={"text": "arm wrestle", "action_type": "social_competition", "target_id": "npc_innkeeper"},
            recent_scene_beats=[
                {"beat_id": "generic_1", "tick": 50, "kind": "activity_beat", "summary": "Captain Aldric scans the tavern.", "tags": [], "actor_id": "npc_guard_captain", "location_id": "loc_tavern"},
                {"beat_id": "generic_2", "tick": 50, "kind": "activity_beat", "summary": "Bran tidies up.", "tags": [], "actor_id": "npc_innkeeper", "location_id": "loc_tavern"},
            ],
            ambient_queue=[
                {"ambient_id": "amb_player", "kind": "player_action_consequence", "text": "A crowd gathers around the contest.", "tick": 50, "priority": 0.9, "location_id": "loc_tavern", "speaker_id": ""},
            ],
        )
        rows = build_incremental_world_event_rows(sim, rt, {})
        # The player consequence should surface prominently
        summaries = [r["summary"] for r in rows]
        assert any("crowd" in s.lower() for s in summaries)


# ── Player world view rows with active player action ────────────────────────

class TestPlayerWorldViewWithActiveAction:
    def test_world_pressure_surfaces_with_player_action(self):
        sim = _sim(tick=50)
        rt = _rt_state(
            tick=50,
            last_player_action={"text": "arm wrestle Bran", "action_type": "social_competition", "target_id": "npc_innkeeper"},
        )
        rt["world_pressure"] = [
            {"pressure_id": "p1", "tick": 50, "kind": "local_attention", "location_id": "loc_tavern", "summary": "Attention builds around the arm wrestling contest.", "intensity": 2, "tags": ["crowd_attention"]},
        ]
        rt["world_rumors"] = [
            {"rumor_id": "r1", "tick": 50, "location_id": "loc_tavern", "summary": "People start talking about the player's strength.", "intensity": 1, "tags": ["rumor_seed"]},
        ]
        rt["recent_world_event_rows"] = [
            {"event_id": "generic1", "scope": "local", "kind": "activity_beat", "title": "Local Activity", "summary": "Captain Aldric scans the tavern.", "tick": 50, "actors": [], "location_id": "loc_tavern", "priority": 0.7, "source": "activity_runtime", "tags": []},
        ]
        rows = build_player_local_world_view_rows(sim, rt)
        # Pressure and rumor rows should appear, and be prioritized
        kinds = [r.get("kind") for r in rows]
        summaries = [r.get("summary", "") for r in rows]
        assert any("world_pressure" in k for k in kinds) or any("attention" in s.lower() for s in summaries)
        assert any("world_rumor" in k for k in kinds) or any("strength" in s.lower() for s in summaries)

    def test_player_action_events_sorted_before_generic_in_view(self):
        sim = _sim(tick=50)
        rt = _rt_state(tick=50)
        rt["world_pressure"] = [
            {"pressure_id": "p1", "tick": 50, "kind": "local_attention", "location_id": "loc_tavern", "summary": "Crowd gathers.", "intensity": 2, "tags": ["crowd_attention"]},
        ]
        rt["recent_world_event_rows"] = [
            {"event_id": "generic1", "scope": "local", "kind": "activity_beat", "title": "Local Activity", "summary": "Bran tidies.", "tick": 50, "actors": [], "location_id": "loc_tavern", "priority": 0.7, "source": "activity_runtime", "tags": []},
            {"event_id": "player1", "scope": "local", "kind": "player_action_consequence", "title": "World Consequence", "summary": "Contest draws attention.", "tick": 50, "actors": [], "location_id": "loc_tavern", "priority": 0.8, "source": "semantic_player_runtime", "tags": ["player_action"]},
        ]
        rows = build_player_local_world_view_rows(sim, rt)
        # Player-related events should appear before generic
        player_idx = None
        generic_idx = None
        for i, r in enumerate(rows):
            if "player_action" in str(r.get("tags", [])) or r.get("source") == "semantic_player_runtime" or r.get("kind") == "world_pressure":
                if player_idx is None:
                    player_idx = i
            elif r.get("source") == "activity_runtime":
                if generic_idx is None:
                    generic_idx = i
        if player_idx is not None and generic_idx is not None:
            assert player_idx < generic_idx, "Player-action events should appear before generic NPC beats"
