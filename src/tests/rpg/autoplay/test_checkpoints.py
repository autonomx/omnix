from pathlib import Path

from tests.rpg.autoplay.checkpoints import (
    collect_state_bounds,
    compare_authoritative_roots,
    load_checkpoint_file,
    stable_json_size,
    validate_save_load_checkpoint,
    write_checkpoint_file,
)


def test_collect_state_bounds_ok_for_small_state():
    state = {"scene": {"location": "Test Tavern"}}

    bounds = collect_state_bounds(state)

    assert bounds["ok"] is True
    assert bounds["state_size_bytes"] == stable_json_size(state)


def test_collect_state_bounds_warns_on_large_state():
    state = {"items": list(range(10))}

    bounds = collect_state_bounds(state, max_list_length=3)

    assert bounds["ok"] is False
    assert "large_list_limit_exceeded" in bounds["warnings"]


def test_compare_authoritative_roots_detects_missing_root():
    before = {"story_arc_state": {"arcs": {"arc:x": {}}}}
    after = {}

    result = compare_authoritative_roots(before, after)

    assert result["ok"] is False
    assert result["missing_roots"] == ["story_arc_state"]


def test_write_and_load_checkpoint_file(tmp_path: Path):
    state = {"scene": {"location": "Test Tavern"}}

    checkpoint = write_checkpoint_file(
        checkpoint_dir=tmp_path,
        session_id="s",
        turn_index=2,
        simulation_state=state,
    )
    loaded = load_checkpoint_file(checkpoint["path"])

    assert checkpoint["ok"] is True
    assert loaded["simulation_state"] == state
    assert loaded["turn_index"] == 2


def test_validate_save_load_checkpoint_roundtrip(monkeypatch, tmp_path: Path):
    from tests.rpg.autoplay import checkpoints

    session_holder = {"state": {}}

    def fake_prepare(*, session_id, simulation_state, reset_session_state=False):
        session_holder["state"] = dict(simulation_state)
        return {"session_id": session_id, "simulation_state": session_holder["state"]}

    monkeypatch.setattr(checkpoints, "prepare_autoplay_manual_session", fake_prepare)
    monkeypatch.setattr(checkpoints, "load_autoplay_simulation_state", lambda session_id: dict(session_holder["state"]))
    monkeypatch.setattr(checkpoints, "load_autoplay_manual_session", lambda session_id: {"simulation_state": dict(session_holder["state"])})

    state = {
        "scene": {"location": "Test Tavern"},
        "story_arc_state": {"arcs": {"arc:x": {"stage": "start"}}},
    }

    result = validate_save_load_checkpoint(
        session_id="s",
        turn_index=1,
        checkpoint_dir=tmp_path,
        simulation_state=state,
    )

    assert result["ok"] is True
    assert result["before_digest"]["hash"] == result["reloaded_digest"]["hash"]