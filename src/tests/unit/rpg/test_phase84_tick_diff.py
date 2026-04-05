from app.rpg.analytics.tick_diff import build_tick_diff


def test_build_tick_diff_basic():
    before = {"tick": 1, "events": [], "consequences": [], "social_state": {}, "sandbox_state": {}, "npc_minds": {}}
    after = {
        "tick": 2,
        "events": [{"type": "x"}],
        "consequences": [{"type": "y"}],
        "social_state": {"rumors": []},
        "sandbox_state": {"world_consequences": []},
        "npc_minds": {"npc1": {"beliefs": {}}},
    }
    diff = build_tick_diff(before, after)
    assert diff["tick_before"] == 1
    assert diff["tick_after"] == 2
    assert len(diff["new_events"]) == 1
    assert len(diff["new_consequences"]) == 1
    assert "npc1" in diff["changed_npc_ids"]


def test_build_tick_diff_no_changes():
    state = {
        "tick": 1,
        "events": [{"type": "x"}],
        "consequences": [{"type": "y"}],
        "social_state": {"a": 1},
        "sandbox_state": {"b": 2},
        "npc_minds": {"npc1": {"beliefs": {}}},
    }
    diff = build_tick_diff(state, state)
    assert diff["tick_before"] == 1
    assert diff["tick_after"] == 1
    assert len(diff["new_events"]) == 0
    assert len(diff["new_consequences"]) == 0
    assert len(diff["social_keys_changed"]) == 0
    assert len(diff["changed_npc_ids"]) == 0


def test_build_tick_diff_npc_changes():
    before = {
        "tick": 1,
        "events": [],
        "consequences": [],
        "social_state": {},
        "sandbox_state": {},
        "npc_minds": {"npc1": {"beliefs": {"trust": 0.1}}},
    }
    after = {
        "tick": 2,
        "events": [],
        "consequences": [],
        "social_state": {},
        "sandbox_state": {},
        "npc_minds": {"npc1": {"beliefs": {"trust": 0.5}}},
    }
    diff = build_tick_diff(before, after)
    assert "npc1" in diff["changed_npc_ids"]


def test_build_tick_diff_social_changes():
    before = {
        "tick": 1,
        "events": [],
        "consequences": [],
        "social_state": {"reputation": {}},
        "sandbox_state": {},
        "npc_minds": {},
    }
    after = {
        "tick": 2,
        "events": [],
        "consequences": [],
        "social_state": {"reputation": {"faction1": 0.5}},
        "sandbox_state": {},
        "npc_minds": {},
    }
    diff = build_tick_diff(before, after)
    assert "reputation" in diff["social_keys_changed"]