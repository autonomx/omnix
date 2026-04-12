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
_rt = _load("app.rpg.session.runtime", "app/rpg/session/runtime.py")
_rp = _load("app.rpg.api.rpg_presentation_routes", "app/rpg/api/rpg_presentation_routes.py")

build_world_events_view = _we.build_world_events_view
build_incremental_world_event_rows = _we.build_incremental_world_event_rows
build_player_world_view_rows = _we.build_player_world_view_rows
get_rpg_session_world_events = _routes.get_rpg_session_world_events
_build_recent_consequence_context = _rp._build_recent_consequence_context
_append_world_rumor = _rt._append_world_rumor
_append_world_pressure = _rt._append_world_pressure
_append_world_consequence = _rt._append_world_consequence
_append_location_condition = _rt._append_location_condition
decay_world_consequences_for_tick = _rt.decay_world_consequences_for_tick
_emit_consequence_world_rows = _rt._emit_consequence_world_rows
_safe_list = _rt._safe_list
_safe_str = _rt._safe_str
_safe_int = _rt._safe_int
_stable_consequence_id = _rt._stable_consequence_id


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


class TestLivingWorldActivityState:
    def test_npc_active_activity_persists_across_ticks(self):
        from app.rpg.session.runtime import (
            advance_actor_activities_for_tick,
            get_actor_activity,
        )
        sim = _sim_state(tick=100, npc_index={"npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"}})
        rt = _runtime_state()
        rt = advance_actor_activities_for_tick(sim, rt)
        first = get_actor_activity(rt, "npc_guard_captain")
        assert first["status"] == "active"

        sim["tick"] = 101
        rt = advance_actor_activities_for_tick(sim, rt)
        second = get_actor_activity(rt, "npc_guard_captain")
        assert second["activity_id"] == first["activity_id"]

    def test_multiple_npcs_can_have_distinct_local_activities(self):
        from app.rpg.session.runtime import advance_actor_activities_for_tick
        sim = _sim_state(
            tick=100,
            npc_index={
                "npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"},
                "npc_innkeeper": {"id": "npc_innkeeper", "name": "Bran", "location_id": "loc_tavern"},
                "npc_merchant": {"id": "npc_merchant", "name": "Elara", "location_id": "loc_tavern"},
            },
        )
        rt = _runtime_state()
        rt = advance_actor_activities_for_tick(sim, rt)
        actor_activities = rt.get("actor_activities", {})
        assert len(actor_activities) >= 2
        summaries = sorted([_we._safe_str(_we._safe_dict(v).get("summary")) for v in actor_activities.values()])
        assert len(set(summaries)) >= 2

    def test_activity_can_generate_world_consequence(self):
        from app.rpg.session.runtime import (
            advance_actor_activities_for_tick,
            emit_activity_beats_for_tick,
        )
        sim = _sim_state(
            tick=100,
            npc_index={"npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"}}
        )
        rt = _runtime_state()
        rt = advance_actor_activities_for_tick(sim, rt)
        rt = emit_activity_beats_for_tick(sim, rt)
        assert len(_we._safe_list(rt.get("recent_world_event_rows"))) >= 1

    def test_session_world_events_route_returns_local_and_global_player_rows(self):
        from app.rpg.session.runtime import ACTIVE_RPG_SESSIONS
        session_id = "test_world_events_local_global_route"
        ACTIVE_RPG_SESSIONS[session_id] = {
            "simulation_state": _sim_state(
                npc_index={"npc_guard_captain": {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"}}
            ),
            "runtime_state": _runtime_state(
                recent_world_event_rows=[
                    {"event_id": "local1", "scope": "local", "kind": "state_change", "title": "NPC Activity", "summary": "Captain Aldric keeps watch.", "tick": 100, "actors": ["npc_guard_captain"], "location_id": "loc_tavern", "priority": 1.0, "status": "active", "source": "semantic_runtime"},
                ],
            ),
        }
        try:
            response = asyncio.run(get_rpg_session_world_events(_DummyRequest({"session_id": session_id})))
            assert response["ok"] is True
            assert "player_local_world_view_rows" in response
            assert "player_global_world_view_rows" in response
        finally:
            ACTIVE_RPG_SESSIONS.pop(session_id, None)


def test_gossip_activity_creates_rumor_consequence():
    from app.rpg.session.runtime import (
        propagate_activity_consequences_for_tick,
        set_actor_activity,
    )
    sim = _sim_state(tick=100)
    rt = _runtime_state()
    rt = set_actor_activity(rt, "npc_innkeeper", {
        "activity_id": "activity_test_gossip",
        "kind": "gossip",
        "summary": "Bran trades rumors with the locals.",
        "location_id": "loc_tavern",
        "target_id": "",
        "target_label": "",
        "started_tick": 100,
        "updated_tick": 100,
        "expected_duration": 2,
        "status": "active",
        "intent": "Learn and spread useful rumors.",
        "world_tags": ["rumor", "social"],
    })
    rt = propagate_activity_consequences_for_tick(sim, rt)
    rumors = _safe_list(rt.get("world_rumors"))
    consequences = _safe_list(rt.get("world_consequences"))
    assert len(rumors) >= 1
    assert any(_safe_str(x.get("kind")) == "rumor" for x in consequences)


def test_patrol_activity_creates_security_pressure():
    from app.rpg.session.runtime import (
        propagate_activity_consequences_for_tick,
        set_actor_activity,
    )
    sim = _sim_state(tick=100)
    rt = _runtime_state()
    rt = set_actor_activity(rt, "npc_guard_captain", {
        "activity_id": "activity_test_patrol",
        "kind": "patrol",
        "summary": "Captain Aldric patrols nearby, watching for trouble.",
        "location_id": "loc_tavern",
        "target_id": "",
        "target_label": "",
        "started_tick": 100,
        "updated_tick": 100,
        "expected_duration": 2,
        "status": "active",
        "intent": "Maintain order and watch for trouble.",
        "world_tags": ["security", "local"],
    })
    rt = propagate_activity_consequences_for_tick(sim, rt)
    pressures = _safe_list(rt.get("world_pressure"))
    assert any(_safe_str(x.get("kind")) == "security_presence" for x in pressures)


def test_global_world_view_rows_include_global_consequences():
    from app.rpg.analytics.world_events import build_player_global_world_view_rows
    sim = _sim_state()
    rt = _runtime_state(world_consequences=[
        {
            "consequence_id": "c1",
            "kind": "market_shift",
            "scope": "global",
            "location_id": "",
            "summary": "Trade shifts local prices and availability.",
            "source_actor_id": "npc_merchant",
            "source_activity_id": "a1",
            "tick": 120,
            "priority": 2,
            "tags": ["commerce"],
        }
    ])
    rows = build_player_global_world_view_rows(sim, rt)
    assert len(rows) >= 1
    assert any(_safe_str(r.get("summary")) == "Trade shifts local prices and availability." for r in rows)


def test_feedback_loop_biases_activity_choice():
    from app.rpg.session.runtime import _choose_activity_kind_for_actor
    actor = {"id": "npc_guard_captain", "name": "Captain Aldric", "location_id": "loc_tavern"}
    rt = _runtime_state(world_pressure=[
        {
            "pressure_id": "p1",
            "kind": "security_presence",
            "scope": "local",
            "location_id": "loc_tavern",
            "value": 3,
            "started_tick": 100,
            "updated_tick": 100,
            "summary": "The local watch grows more visible and alert.",
            "tags": ["security"],
        }
    ])
    kind = _choose_activity_kind_for_actor(actor, 101, rt)
    assert kind in ("patrol", "watch_crowd", "question_patron")


def test_rumor_aggregation_increases_strength():
    rt = _runtime_state()
    rumor = {
        "rumor_id": "r1",
        "summary": "Rumors spread among the locals.",
        "scope": "local",
        "location_id": "loc_tavern",
        "source_actor_id": "npc_innkeeper",
        "source_kind": "gossip",
        "started_tick": 100,
        "updated_tick": 100,
        "strength": 1,
        "tags": ["rumor"],
    }
    rt = _append_world_rumor(rt, rumor)
    rt = _append_world_rumor(rt, dict(rumor, rumor_id="r2", updated_tick=101, strength=1))
    rumors = _safe_list(rt.get("world_rumors"))
    assert len(rumors) == 1
    assert _safe_int(rumors[0].get("strength"), 0) >= 2


def test_pressure_aggregation_increases_value():
    rt = _runtime_state()
    pressure = {
        "pressure_id": "p1",
        "kind": "security_presence",
        "scope": "local",
        "location_id": "loc_tavern",
        "value": 1,
        "started_tick": 100,
        "updated_tick": 100,
        "summary": "The local watch grows more visible and alert.",
        "tags": ["security"],
    }
    rt = _append_world_pressure(rt, pressure)
    rt = _append_world_pressure(rt, dict(pressure, pressure_id="p2", updated_tick=101, value=1))
    pressures = _safe_list(rt.get("world_pressure"))
    assert len(pressures) == 1
    assert _safe_int(pressures[0].get("value"), 0) >= 2


def test_rumor_decay_reduces_strength():
    sim = _sim_state(tick=110)
    rt = _runtime_state(world_rumors=[
        {
            "rumor_id": "r1",
            "summary": "Rumors spread among the locals.",
            "scope": "local",
            "location_id": "loc_tavern",
            "source_actor_id": "npc_innkeeper",
            "source_kind": "gossip",
            "started_tick": 100,
            "updated_tick": 100,
            "strength": 2,
            "tags": ["rumor"],
        }
    ])
    rt = decay_world_consequences_for_tick(sim, rt)
    rumors = _safe_list(rt.get("world_rumors"))
    assert len(rumors) == 1
    assert _safe_int(rumors[0].get("strength"), 0) == 1


def test_pressure_decay_reduces_value():
    sim = _sim_state(tick=110)
    rt = _runtime_state(world_pressure=[
        {
            "pressure_id": "p1",
            "kind": "security_presence",
            "scope": "local",
            "location_id": "loc_tavern",
            "value": 2,
            "started_tick": 100,
            "updated_tick": 100,
            "summary": "The local watch grows more visible and alert.",
            "tags": ["security"],
        }
    ])
    rt = decay_world_consequences_for_tick(sim, rt)
    pressures = _safe_list(rt.get("world_pressure"))
    assert len(pressures) == 1
    assert _safe_int(pressures[0].get("value"), 0) == 1


def test_consequence_feed_rows_update_in_place():
    rt = _runtime_state(recent_world_event_rows=[])
    consequence = {
        "consequence_id": "c1",
        "kind": "security_pressure",
        "scope": "local",
        "location_id": "loc_tavern",
        "summary": "The local watch grows more visible and alert.",
        "source_actor_id": "npc_guard_captain",
        "source_activity_id": "a1",
        "tick": 100,
        "priority": 2,
        "tags": ["security"],
    }
    rt = _emit_consequence_world_rows(rt, consequence)
    rt = _emit_consequence_world_rows(rt, dict(consequence, tick=101))
    rows = _safe_list(rt.get("recent_world_event_rows"))
    assert len(rows) == 1
    assert _safe_int(rows[0].get("tick"), 0) == 101


def test_world_consequence_aggregation_merges_same_summary_and_scope():
    rt = _runtime_state()
    consequence = {
        "consequence_id": "c1",
        "kind": "security_pressure",
        "scope": "local",
        "location_id": "loc_tavern",
        "summary": "The local watch grows more visible and alert.",
        "source_actor_id": "npc_guard_captain",
        "tick": 100,
        "priority": 2,
        "tags": ["security"],
    }
    rt = _append_world_consequence(rt, consequence)
    rt = _append_world_consequence(rt, dict(consequence, consequence_id="c2", tick=101, priority=3))
    consequences = _safe_list(rt.get("world_consequences"))
    assert len(consequences) == 1
    assert _safe_int(consequences[0].get("priority"), 0) >= 3


def test_location_condition_aggregation_refreshes_existing_condition():
    rt = _runtime_state()
    condition = {
        "condition_id": "cond1",
        "location_id": "loc_tavern",
        "kind": "orderly",
        "summary": "The area feels more orderly and well-kept.",
        "severity": 1,
        "started_tick": 100,
        "updated_tick": 100,
        "status": "active",
        "tags": ["order"],
    }
    rt = _append_location_condition(rt, condition)
    rt = _append_location_condition(rt, dict(condition, condition_id="cond2", updated_tick=101, severity=2))
    conditions = _safe_list(rt.get("location_conditions"))
    assert len(conditions) == 1
    assert _safe_int(conditions[0].get("severity"), 0) >= 2


def test_consequence_decay_eventually_removes_stale_records():
    sim = _sim_state(tick=120)  # 20 ticks later
    rt = _runtime_state(world_consequences=[
        {
            "consequence_id": "c1",
            "kind": "security_pressure",
            "scope": "local",
            "location_id": "loc_tavern",
            "summary": "The local watch grows more visible and alert.",
            "tick": 100,
            "priority": 2,
            "tags": ["security"],
        }
    ])
    rt = decay_world_consequences_for_tick(sim, rt)
    consequences = _safe_list(rt.get("world_consequences"))
    assert len(consequences) == 0  # Should be decayed away


def test_recent_consequence_context_includes_local_pressure_and_conditions():
    rt = _runtime_state()
    # Add some test data
    rt["world_pressure"] = [{
        "kind": "security_presence",
        "location_id": "loc_tavern",
        "value": 3,
        "summary": "High security presence",
    }]
    rt["location_conditions"] = [{
        "kind": "orderly",
        "location_id": "loc_tavern",
        "severity": 2,
        "summary": "Area is well-maintained",
    }]
    rt["world_consequences"] = [{
        "kind": "test",
        "location_id": "loc_tavern",
        "summary": "Test consequence",
        "tick": 100,
    }]

    context = _build_recent_consequence_context(rt, "actor1", "loc_tavern")
    assert "recent_consequences" in context
    assert "local_pressure" in context
    assert "local_conditions" in context
    assert len(context["local_pressure"]) > 0
    assert len(context["local_conditions"]) > 0


def test_consequence_ids_are_stable_for_same_logical_event():
    # Test that same logical consequence gets same ID
    id1 = _rt._stable_consequence_id("consequence", 100, "local", "tavern", "watch alert")
    id2 = _rt._stable_consequence_id("consequence", 101, "local", "tavern", "watch alert")
    assert id1 == id2  # Should be stable despite different ticks
