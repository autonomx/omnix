"""Functional tests — World Events view builder."""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, SRC_DIR)


def _load(mod_name: str, rel_path: str):
    """Load a module by file path to avoid interference from stub finders."""
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(SRC_DIR, rel_path),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_routes = _load("app.rpg.api.rpg_session_routes", "app/rpg/api/rpg_session_routes.py")
_we = _load("app.rpg.analytics.world_events", "app/rpg/analytics/world_events.py")

build_world_events_view = _we.build_world_events_view
build_incremental_world_event_rows = _we.build_incremental_world_event_rows
build_player_world_view_rows = _we.build_player_world_view_rows
get_rpg_session_world_events = _routes.get_rpg_session_world_events


def _sim_state(**overrides):
    state = {
        "tick": 10,
        "player_state": {"location_id": "loc:market"},
        "events": [
            {"event_id": "e1", "type": "arrive", "location_id": "loc:market", "description": "A merchant arrives.", "tick": 9},
            {"event_id": "e2", "type": "threat", "location_id": "loc:forest", "description": "Wolves howl.", "tick": 8},
        ],
        "incidents": [
            {"incident_id": "i1", "location_id": "loc:market", "description": "Brawl breaks out.", "tick": 10},
        ],
        "sandbox_state": {
            "world_consequences": [
                {"consequence_id": "wc1", "type": "Trade disrupted", "description": "Trade routes blocked.", "tick": 9},
            ],
        },
        "faction_pressure": {
            "guards": {"name": "City Guard", "level": 0.7, "location_id": "loc:market"},
        },
        "threads": [
            {"thread_id": "t1", "name": "Conspiracy", "summary": "Shadowy plot.", "tick": 8},
        ],
        "arc_control": {"current_arc": "The Dark Reckoning"},
        "narrative_pressure": {"level": 0.6},
    }
    state.update(overrides)
    return state


def _runtime_state(**overrides):
    state = {
        "ambient_queue": [],
        "recent_world_event_rows": [],
        "opening_runtime": {"active": False},
    }
    state.update(overrides)
    return state


class TestBuildWorldEventsView:
    def test_returns_all_sections(self):
        sim = _sim_state()
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        assert "local_events" in view
        assert "global_events" in view
        assert "director_pressure" in view
        assert "recent_changes" in view
        assert "current_tick" in view

    def test_local_events_bounded(self):
        events = [
            {"event_id": f"e{i}", "type": "arrive", "location_id": "loc:market", "description": f"Event {i}", "tick": i}
            for i in range(30)
        ]
        sim = _sim_state(events=events)
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        assert len(view["local_events"]) <= 12

    def test_global_events_bounded(self):
        wc = [
            {"consequence_id": f"wc{i}", "type": "change", "description": f"Change {i}", "tick": i}
            for i in range(20)
        ]
        sim = _sim_state()
        sim["sandbox_state"] = {"world_consequences": wc}
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        assert len(view["global_events"]) <= 12

    def test_director_bounded(self):
        sim = _sim_state()
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        assert len(view["director_pressure"]) <= 12


class TestDirectorSeparation:
    def test_director_rows_have_correct_scope(self):
        sim = _sim_state()
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        for row in view["director_pressure"]:
            assert row["scope"] == "director"
            assert row["source"] == "director_bias"

    def test_local_events_not_director(self):
        sim = _sim_state()
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        for row in view["local_events"]:
            assert row["scope"] != "director"

    def test_global_events_not_director(self):
        sim = _sim_state()
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        for row in view["global_events"]:
            assert row["scope"] != "director"


class TestDeterministicOrdering:
    def test_local_events_sorted(self):
        sim = _sim_state()
        rt = _runtime_state()
        view = build_world_events_view(sim, rt)
        events = view["local_events"]
        if len(events) > 1:
            for i in range(len(events) - 1):
                # Priority descending (higher first)
                assert events[i]["priority"] >= events[i + 1]["priority"] or events[i]["tick"] <= events[i + 1]["tick"]


class TestEmptyInputsSafe:
    def test_empty_simulation_state(self):
        view = build_world_events_view({}, {})
        assert view["local_events"] == []
        assert view["global_events"] == []
        assert view["director_pressure"] == []
        assert view["recent_changes"] == []

    def test_none_inputs(self):
        view = build_world_events_view(None, None)
        assert isinstance(view, dict)


class TestIncrementalRows:
    def test_incremental_from_ambient_queue(self):
        rt = _runtime_state(ambient_queue=[
            {"ambient_id": "a1", "kind": "follow_reaction", "text": "Bran follows.", "tick": 10, "priority": 0.7, "location_id": "loc:cave", "speaker_id": "npc:bran"},
        ])
        sim = _sim_state()
        rows = build_incremental_world_event_rows(sim, rt, {})
        assert len(rows) >= 1
        assert rows[0]["kind"] == "follow_reaction"

    def test_incremental_bounded(self):
        queue = [
            {"ambient_id": f"a{i}", "kind": "world_event", "text": f"Event {i}", "tick": 10, "priority": 0.3, "location_id": "loc:x", "speaker_id": ""}
            for i in range(20)
        ]
        rt = _runtime_state(ambient_queue=queue)
        sim = _sim_state()
        rows = build_incremental_world_event_rows(sim, rt, {})
        assert len(rows) <= 8


class TestPlayerWorldViewNormalization:
    def test_build_player_world_view_rows_merges_state_change_and_scene_beat_pair(self):
        sim = _sim_state(npcs={"npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric"}})
        rt = _runtime_state(recent_world_event_rows=[
            {
                "event_id": "state1",
                "scope": "local",
                "kind": "state_change",
                "title": "NPC Activity",
                "summary": "Captain Aldric scans the tavern crowd with a watchful eye.",
                "tick": 100,
                "actors": ["npc_guard_captain"],
                "location_id": "loc_tavern",
                "priority": 0.65,
                "source": "semantic_runtime",
            },
            {
                "event_id": "scene1",
                "scope": "local",
                "kind": "state_change_beat",
                "title": "Scene Development",
                "summary": "Captain Aldric scans the tavern crowd with a watchful eye.",
                "tick": 100,
                "actors": ["npc_guard_captain"],
                "location_id": "loc_tavern",
                "priority": 0.55,
                "source": "scene_beats",
            },
        ])
        rows = build_player_world_view_rows(sim, rt)
        assert len(rows) == 1
        row = rows[0]
        assert row["kind"] == "world_view_activity"
        assert row["title"] == "Captain Aldric"
        assert row["summary"] == "Captain Aldric scans the tavern crowd with a watchful eye."
        assert row["source"] == "world_view_merged"
        assert "actor_label" in row
        assert row["actor_label"] == "Captain Aldric"

    def test_build_player_world_view_rows_suppresses_near_identical_repetition(self):
        sim = _sim_state()
        rt = _runtime_state(recent_world_event_rows=[
            {
                "event_id": "e1",
                "scope": "local",
                "kind": "world_view_activity",
                "title": "Captain Aldric",
                "summary": "scans the tavern crowd",
                "tick": 104,
                "actor_label": "Captain Aldric",
                "location_id": "loc_tavern",
                "priority": 0.6,
            },
            {
                "event_id": "e2",
                "scope": "local",
                "kind": "world_view_activity",
                "title": "Captain Aldric",
                "summary": "scans the tavern crowd",
                "tick": 102,
                "actor_label": "Captain Aldric",
                "location_id": "loc_tavern",
                "priority": 0.6,
            },
            {
                "event_id": "e3",
                "scope": "local",
                "kind": "world_view_activity",
                "title": "Captain Aldric",
                "summary": "scans the tavern crowd",
                "tick": 100,
                "actor_label": "Captain Aldric",
                "location_id": "loc_tavern",
                "priority": 0.6,
            },
        ])
        rows = build_player_world_view_rows(sim, rt)
        assert len(rows) == 1
        assert rows[0]["tick"] == 104  # newest

    def test_build_player_world_view_rows_keeps_meaningfully_different_events(self):
        sim = _sim_state()
        rt = _runtime_state(recent_world_event_rows=[
            {
                "event_id": "e1",
                "scope": "local",
                "kind": "world_view_activity",
                "title": "Captain Aldric",
                "summary": "scans the tavern crowd",
                "tick": 110,
                "actor_label": "Captain Aldric",
                "location_id": "loc_tavern",
            },
            {
                "event_id": "e2",
                "scope": "local",
                "kind": "world_view_activity",
                "title": "Captain Aldric",
                "summary": "surveys the tavern floor",
                "tick": 105,
                "actor_label": "Captain Aldric",
                "location_id": "loc_tavern",
            },
        ])
        rows = build_player_world_view_rows(sim, rt)
        assert len(rows) == 2

    def test_build_player_world_view_rows_capped_to_8(self):
        sim = _sim_state()
        rows = [
            {
                "event_id": f"e{i}",
                "scope": "local",
                "kind": "world_view_activity",
                "title": f"Event {i}",
                "summary": f"Summary {i}",
                "tick": 100 + i,
                "actor_label": "",
                "location_id": "loc_tavern",
            }
            for i in range(15)
        ]
        rt = _runtime_state(recent_world_event_rows=rows)
        result = build_player_world_view_rows(sim, rt)
        assert len(result) <= 8

    def test_build_player_world_view_rows_newest_first(self):
        sim = _sim_state()
        rt = _runtime_state(recent_world_event_rows=[
            {"event_id": "e1", "tick": 100, "scope": "local", "kind": "world_view_activity", "title": "Old", "summary": "old", "actor_label": "", "location_id": ""},
            {"event_id": "e2", "tick": 110, "scope": "local", "kind": "world_view_activity", "title": "New", "summary": "new", "actor_label": "", "location_id": ""},
        ])
        rows = build_player_world_view_rows(sim, rt)
        assert rows[0]["tick"] == 110
        assert rows[1]["tick"] == 100


class _DummyRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class TestWorldEventsRoute:
    def test_session_world_events_route_returns_player_world_view_rows(self):
        from app.rpg.session.runtime import ACTIVE_RPG_SESSIONS

        session_id = "test_world_events_route"
        ACTIVE_RPG_SESSIONS[session_id] = {
            "simulation_state": _sim_state(
                npcs={"npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric"}}
            ),
            "runtime_state": _runtime_state(recent_world_event_rows=[
                {"event_id": "scene1", "scope": "local", "kind": "state_change_beat", "title": "Scene Development", "summary": "Captain Aldric scans the tavern crowd with a watchful eye.", "tick": 100, "actors": [], "location_id": "loc_tavern", "priority": 1.0, "status": "active", "source": "scene_beats"},
                {"event_id": "state1", "scope": "local", "kind": "state_change", "title": "NPC Activity", "summary": "Captain Aldric scans the tavern crowd with a watchful eye.", "tick": 100, "actors": ["npc_guard_captain"], "location_id": "loc_tavern", "priority": 1.0, "status": "active", "source": "semantic_runtime"},
            ]),
        }
        try:
            response = asyncio.run(get_rpg_session_world_events(_DummyRequest({"session_id": session_id})))
            assert response["ok"] is True
            assert "recent_world_event_rows" in response
            assert "player_world_view_rows" in response
            assert len(response["player_world_view_rows"]) == 1
        finally:
            ACTIVE_RPG_SESSIONS.pop(session_id, None)
