from __future__ import annotations

from app.rpg.replay_contracts import (
    ReplaySnapshot,
    build_regression_scenario,
    compare_snapshot_hashes,
    replay_report_payload,
    validate_snapshot,
)


def _snapshot() -> ReplaySnapshot:
    return ReplaySnapshot(
        "snap-1",
        4,
        123,
        {"rng": 2},
        {"world": {}, "player": {}, "quests": {}, "map": {}, "inventory": {"gold": 1}},
    )


def test_snapshot_hash_is_stable_for_key_order() -> None:
    left = _snapshot()
    right = ReplaySnapshot(
        "snap-1",
        4,
        123,
        {"rng": 2},
        {"inventory": {"gold": 1}, "map": {}, "quests": {}, "player": {}, "world": {}},
    )

    assert left.stable_hash() == right.stable_hash()


def test_compare_snapshot_hashes_reports_match() -> None:
    report = compare_snapshot_hashes(_snapshot(), _snapshot())

    assert report["matches"] is True
    assert report["expected_hash"] == report["actual_hash"]


def test_build_regression_scenario_numbers_actions() -> None:
    scenario = build_regression_scenario("shop", 7, ["look", "buy ration"])

    assert scenario.seed == 7
    assert scenario.actions[1].turn == 2
    assert scenario.as_dict()["actions"][0]["action"] == "look"


def test_validate_snapshot_requires_core_sections() -> None:
    assert validate_snapshot(_snapshot()) == ()
    assert "missing_state:inventory" in validate_snapshot(ReplaySnapshot("snap", 0, 1, state={}))


def test_replay_report_payload_includes_hash_and_validation() -> None:
    payload = replay_report_payload(_snapshot(), build_regression_scenario("basic", 1, ["look"]))

    assert payload["snapshot_id"] == "snap-1"
    assert payload["state_hash"]
    assert payload["validation_issues"] == []
