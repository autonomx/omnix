import json
import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_inspect_timeline_route(client):
    payload = {"setup_payload": {"metadata": {"simulation_state": {"tick": 1}}}}
    res = client.post("/api/rpg/inspect/timeline", data=json.dumps(payload), content_type="application/json")
    data = res.get_json()
    assert res.status_code == 200
    assert data["ok"] is True
    assert "timeline" in data


def test_inspect_npc_reasoning_route(client):
    payload = {
        "setup_payload": {
            "metadata": {
                "simulation_state": {
                    "npc_index": {"npc1": {"name": "Guard"}},
                    "npc_minds": {"npc1": {"beliefs": {}}},
                }
            }
        },
        "npc_id": "npc1",
    }
    res = client.post("/api/rpg/inspect/npc_reasoning", data=json.dumps(payload), content_type="application/json")
    data = res.get_json()
    assert res.status_code == 200
    assert data["ok"] is True
    assert data["npc_reasoning"]["npc"]["name"] == "Guard"


def test_inspect_tick_diff_route(client):
    payload = {
        "before_state": {"tick": 1, "events": [], "consequences": [], "social_state": {}, "sandbox_state": {}, "npc_minds": {}},
        "after_state": {"tick": 2, "events": [{"type": "x"}], "consequences": [], "social_state": {}, "sandbox_state": {}, "npc_minds": {}},
    }
    res = client.post("/api/rpg/inspect/tick_diff", data=json.dumps(payload), content_type="application/json")
    data = res.get_json()
    assert res.status_code == 200
    assert data["ok"] is True
    assert data["tick_diff"]["tick_before"] == 1
    assert data["tick_diff"]["tick_after"] == 2


def test_gm_force_npc_goal_route(client):
    payload = {
        "setup_payload": {
            "metadata": {
                "simulation_state": {
                    "npc_minds": {"npc1": {"goals": []}},
                }
            }
        },
        "npc_id": "npc1",
        "goal": {"goal_id": "g1", "priority": 1},
    }
    res = client.post("/api/rpg/gm/force_npc_goal", data=json.dumps(payload), content_type="application/json")
    data = res.get_json()
    assert res.status_code == 200
    assert data["ok"] is True
    assert len(data["setup_payload"]["metadata"]["simulation_state"]["npc_minds"]["npc1"]["goals"]) == 1


def test_gm_force_faction_trend_route(client):
    payload = {
        "setup_payload": {
            "metadata": {
                "simulation_state": {
                    "sandbox_state": {},
                }
            }
        },
        "faction_id": "faction1",
        "trend_patch": {"aggression": 0.5},
    }
    res = client.post("/api/rpg/gm/force_faction_trend", data=json.dumps(payload), content_type="application/json")
    data = res.get_json()
    assert res.status_code == 200
    assert data["ok"] is True
    sandbox = data["setup_payload"]["metadata"]["simulation_state"]["sandbox_state"]
    assert sandbox["faction_trends"]["faction1"]["aggression"] == 0.5


def test_gm_debug_note_route(client):
    payload = {
        "setup_payload": {
            "metadata": {
                "simulation_state": {
                    "debug_meta": {},
                }
            }
        },
        "note": "Test note",
    }
    res = client.post("/api/rpg/gm/debug_note", data=json.dumps(payload), content_type="application/json")
    data = res.get_json()
    assert res.status_code == 200
    assert data["ok"] is True
    notes = data["setup_payload"]["metadata"]["simulation_state"]["debug_meta"]["gm_notes"]
    assert len(notes) == 1
    assert notes[0]["note"] == "Test note"