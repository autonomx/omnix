from app.rpg.analytics.npc_reasoning import inspect_npc_reasoning


def test_inspect_npc_reasoning_basic():
    state = {
        "npc_index": {
            "npc1": {"name": "Guard", "role": "guard", "faction_id": "watch", "location_id": "gate"}
        },
        "npc_minds": {
            "npc1": {
                "beliefs": {"player": {"trust": 0.1}},
                "goals": [{"goal_id": "g1"}],
                "memory": {"entries": [{"summary": "x"}]},
                "last_decision": {"reason": "Suspicious"},
            }
        },
        "social_state": {"group_positions": {"watch": {"stance": "watch"}}},
    }
    out = inspect_npc_reasoning(state, "npc1")
    assert out["npc"]["name"] == "Guard"
    assert out["reasoning"]["faction_position"]["stance"] == "watch"


def test_inspect_npc_reasoning_missing_npc():
    state = {
        "npc_index": {},
        "npc_minds": {},
        "social_state": {},
    }
    out = inspect_npc_reasoning(state, "unknown")
    assert out["npc"]["npc_id"] == "unknown"
    assert out["npc"]["name"] == "unknown"


def test_inspect_npc_reasoning_minimal_state():
    state = {}
    out = inspect_npc_reasoning(state, "npc1")
    assert out["npc"]["npc_id"] == "npc1"
    assert out["reasoning"]["beliefs"] == {}
    assert out["reasoning"]["top_goals"] == []
    assert out["reasoning"]["recent_memories"] == []