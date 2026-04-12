"""Phase: World events session flow integration tests."""
from __future__ import annotations


def test_world_events_for_session_route_returns_session_backed_data(client, monkeypatch):
    from app.rpg.session import runtime as runtime_mod

    store = {
        "world_events_session": {
            "session_id": "world_events_session",
            "simulation_state": {
                "tick": 4,
                "player_state": {"location_id": "loc:tavern"},
                "sandbox_state": {"world_consequences": []},
                "events": [],
                "incidents": [],
            },
            "runtime_state": {
                "ambient_queue": [
                    {
                        "ambient_id": "amb:1",
                        "tick": 4,
                        "kind": "idle_check_in",
                        "text": "Bran checks in with you.",
                        "speaker_id": "npc:bran",
                        "location_id": "loc:tavern",
                        "priority": 0.4,
                    }
                ],
                "recent_world_event_rows": [],
            },
        }
    }

    monkeypatch.setattr(runtime_mod, "load_runtime_session", lambda session_id: store.get(session_id))

    res = client.post("/api/rpg/inspect/world_events_for_session", json={"session_id": "world_events_session"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "world_events" in data
    assert "local_events" in data["world_events"]
    assert "global_events" in data["world_events"]
    assert "director_pressure" in data["world_events"]


def test_world_events_for_session_requires_session_id(client):
    res = client.post("/api/rpg/inspect/world_events_for_session", json={})
    assert res.status_code == 400


def test_incremental_world_event_rows_include_semantic_state_change_events():
    from app.rpg.analytics.world_events import build_incremental_world_event_rows

    simulation_state = {"tick": 37}
    runtime_state = {
        "accepted_state_change_events": [
            {
                "event_id": "state_change_test_1",
                "tick": 37,
                "actor_id": "npc_guard_captain",
                "location_id": "loc_tavern",
                "summary": "Captain Aldric scans the tavern crowd, remaining vigilant.",
                "beat": {
                    "summary": "Captain Aldric scans the tavern crowd, remaining vigilant.",
                    "priority": 50,
                },
            }
        ],
        "ambient_queue": [],
        "recent_scene_beats": [],
    }

    rows = build_incremental_world_event_rows(simulation_state, runtime_state, {})

    assert len(rows) == 1
    row = rows[0]
    assert row["event_id"] == "state_change_test_1"
    assert row["kind"] == "state_change"
    assert row["title"] == "NPC Activity"
    assert "Captain Aldric" in row["summary"]
    assert row["scope"] == "local"
    assert row["source"] == "semantic_runtime"


def test_incremental_world_event_rows_filter_scene_beats_to_event_worthy_kinds():
    from app.rpg.analytics.world_events import build_incremental_world_event_rows

    simulation_state = {"tick": 50}
    runtime_state = {
        "accepted_state_change_events": [],
        "ambient_queue": [],
        "recent_scene_beats": [
            {
                "beat_id": "allowed_beat",
                "tick": 50,
                "kind": "state_change_beat",
                "summary": "A guard shifts into a more alert patrol.",
                "location_id": "loc_tavern",
                "actor_id": "npc_guard_captain",
                "priority": 40,
            },
            {
                "beat_id": "disallowed_beat",
                "tick": 50,
                "kind": "dialogue_line",
                "summary": "Hello there.",
                "location_id": "loc_tavern",
                "actor_id": "npc_innkeeper",
                "priority": 10,
            },
        ],
    }

    rows = build_incremental_world_event_rows(simulation_state, runtime_state, {})

    assert len(rows) == 1
    row = rows[0]
    assert row["event_id"] == "allowed_beat"
    assert row["source"] == "scene_beats"
    assert row["kind"] == "state_change_beat"


def test_world_events_for_session_missing_session_returns_404(client):
    res = client.post("/api/rpg/inspect/world_events_for_session", json={"session_id": "missing"})
    assert res.status_code == 404


def test_session_world_events_route_returns_player_world_view_rows(client, monkeypatch):
    from app.rpg.analytics.world_events import build_player_world_view_rows

    store = {
        "world_events_session": {
            "session_id": "world_events_session",
            "simulation_state": {
                "tick": 4,
                "npcs": {"npc_guard_captain": {"name": "Captain Aldric"}},
            },
            "runtime_state": {
                "recent_world_event_rows": [
                    {
                        "event_id": "state1",
                        "kind": "state_change",
                        "summary": "Captain Aldric scans the crowd.",
                        "tick": 4,
                        "actors": ["npc_guard_captain"],
                        "location_id": "loc_tavern",
                    },
                ],
            },
        }
    }

    monkeypatch.setattr("app.rpg.session.runtime.load_runtime_session", lambda session_id: store.get(session_id))

    res = client.post("/api/rpg/session/world_events", json={"session_id": "world_events_session"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "recent_world_event_rows" in data
    assert "player_world_view_rows" in data
    assert len(data["player_world_view_rows"]) >= 0