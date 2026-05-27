from __future__ import annotations

import json
from pathlib import Path

import pytest

_ORIGINAL_WRITE_TEXT = Path.write_text
_FRAGMENT = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts" / "zzzzzzzzzzzzzzzzzzzzzzzzzzzz_bundle_ar3_concrete_survival_action_injection.pyfrag"


@pytest.fixture(autouse=True)
def _restore_write_text():
    Path.write_text = _ORIGINAL_WRITE_TEXT
    yield
    Path.write_text = _ORIGINAL_WRITE_TEXT


def _load_ns():
    ns = {"__name__": "_bundle_ar3_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), ns, ns)
    return ns


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    _ORIGINAL_WRITE_TEXT(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_bundle_ar3_selects_missing_action_sequence():
    ns = _load_ns()
    choose = ns["_bundle_ar3_action_for_counts"]
    assert choose({"drink_water_count": 0, "eat_food_count": 0, "rest_count": 0}) == "drink water from my waterskin"
    assert choose({"drink_water_count": 1, "eat_food_count": 0, "rest_count": 0}) == "eat rations from my pack"
    assert choose({"drink_water_count": 1, "eat_food_count": 1, "rest_count": 0}) == "rest at camp until recovered"
    assert choose({"drink_water_count": 1, "eat_food_count": 1, "rest_count": 1}) == ""


def test_bundle_ar3_player_payload_gets_first_missing_action(tmp_path):
    _load_ns()
    root = tmp_path / "run" / "autoplay-campaign-results-unzipped"
    _write_json(root / "survival-exit-criteria-summary.json", {"drink_water_count": 0, "eat_food_count": 0, "rest_count": 0})
    payload_path = root / "player-action-context.json"
    payload_path.write_text(json.dumps({"candidate_actions": [{"action": "secure records"}]}), encoding="utf-8")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["candidate_actions"][0]["action"] == "drink water from my waterskin"
    assert payload["survival_action_injection"]["active"] is True


def test_bundle_ar3_no_payload_change_after_all_evidence_exists(tmp_path):
    _load_ns()
    root = tmp_path / "run" / "autoplay-campaign-results-unzipped"
    _write_json(root / "survival-exit-criteria-summary.json", {"drink_water_count": 1, "eat_food_count": 1, "rest_count": 1})
    payload_path = root / "player-action-context.json"
    payload_path.write_text(json.dumps({"candidate_actions": [{"action": "secure records"}]}), encoding="utf-8")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["candidate_actions"][0]["action"] == "secure records"
    assert "survival_action_injection" not in payload
