from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest


_ORIGINAL_PATH_WRITE_TEXT = Path.write_text

_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzzzzzzzzzzzzzzz_bundle_ar_survival_autoplay_evidence.pyfrag"
)


@pytest.fixture(autouse=True)
def _restore_bundle_ar_path_write_text():
    """Keep AR's global Path.write_text hook from leaking into AP/AQ tests."""
    Path.write_text = _ORIGINAL_PATH_WRITE_TEXT
    yield
    Path.write_text = _ORIGINAL_PATH_WRITE_TEXT


def _load_bundle_ar_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ar_survival_autoplay_evidence_test"}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_report_case(directory: Path):
    _write_json(
        directory / "readiness-report-projection-summary.json",
        {
            "ok": False,
            "advisory_ok": True,
            "checks": {"all_report_sections_ok": False, "survival_exit_criteria_ok": False},
            "failed_checks": ["survival-exit-criteria", "all_report_sections_ok", "survival_autoplay_evidence_ok"],
            "remaining_real_gameplay_blockers": ["survival-exit-criteria"],
            "sections": [
                {"id": "content-exhaustion-forecast", "ok": True, "artifact_ok": True, "advisory_ok": True, "summary": {}},
                {"id": "survival-exit-criteria", "ok": False, "artifact_ok": False, "advisory_ok": False, "summary": {}},
            ],
        },
    )
    _write_json(directory / "autoplay-health.json", {"ok": True, "survival_exit_criteria_ok": False})
    _write_json(directory / "survival-exit-criteria-summary.json", {"ok": False, "drink_water_count": 0, "eat_food_count": 0, "rest_count": 0})


def _seed_output(parent: Path, with_actions: bool = True):
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    rows = []
    if with_actions:
        rows = [
            {"turn": 8, "player_action": "drink water from my waterskin", "needs": {"thirst": 0.8}},
            {"turn": 19, "player_action": "eat rations from my pack", "needs": {"hunger": 0.74}},
            {"turn": 31, "player_action": "rest at the inn until morning", "needs": {"fatigue": 0.7}},
        ]
    for directory in (parent, unzipped):
        _seed_report_case(directory)
        _write_json(directory / "transcript.json", {"rows": rows})


def test_bundle_ar_selects_survival_pressure_actions_from_needs():
    namespace = _load_bundle_ar_namespace()
    choose = namespace["_bundle_ar_survival_pressure_action"]

    assert choose({"needs": {"thirst": 0.8}, "inventory": {"waterskin": 1}}) == "drink water"
    assert choose({"needs": {"thirst": 0.8}, "inventory": {}}) == "buy water"
    assert choose({"needs": {"hunger": 0.7}, "inventory": {"rations": 2}}) == "eat rations"
    assert choose({"needs": {"hunger": 0.7}, "inventory": {}}) == "buy rations"
    assert choose({"needs": {"fatigue": 0.9}, "inventory": {}}) == "rest"


def test_bundle_ar_injects_survival_actions_into_advisory_payload():
    namespace = _load_bundle_ar_namespace()
    patch = namespace["_bundle_ar_patch_advisory_payload"]

    payload = {"state": {"needs": {"thirst": 0.9}, "inventory": {"water flask": 1}}, "suggested_actions": [{"action": "ask Bran about work"}]}
    patched = patch(payload)

    assert patched["bundle_ar_survival_pressure_applied"] is True
    assert patched["survival_pressure"]["action"] == "drink water"
    assert patched["suggested_actions"][0]["action"] == "drink water"
    assert patched["recommended_next_actions"][0]["action"] == "drink water"
    assert patched["candidate_actions"][0]["action"] == "drink water"


def test_bundle_ar_summary_passes_from_real_transcript_evidence(tmp_path):
    namespace = _load_bundle_ar_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_output(parent, with_actions=True)

    result = namespace["_bundle_ar_finalize_output_dir"](str(parent))

    assert result["ok"] is True
    unzipped = parent / "autoplay-campaign-results-unzipped"
    survival = json.loads((unzipped / "survival-exit-criteria-summary.json").read_text(encoding="utf-8"))
    report = json.loads((unzipped / "readiness-report-projection-summary.json").read_text(encoding="utf-8"))
    health = json.loads((unzipped / "autoplay-health.json").read_text(encoding="utf-8"))

    assert survival["ok"] is True
    assert survival["drink_water_count"] >= 1
    assert survival["eat_food_count"] >= 1
    assert survival["rest_count"] >= 1
    assert survival["checks"]["survival_metric_source_ok"] is True
    sections = {section["id"]: section for section in report["sections"]}
    assert sections["survival-exit-criteria"]["ok"] is True
    assert report["remaining_real_gameplay_blockers"] == []
    assert "survival-exit-criteria" not in report["failed_checks"]
    assert health["survival_exit_criteria_ok"] is True


def test_bundle_ar_does_not_pass_without_real_drink_eat_rest_actions(tmp_path):
    namespace = _load_bundle_ar_namespace()
    parent = tmp_path / "autoplay-output"
    _seed_output(parent, with_actions=False)

    result = namespace["_bundle_ar_finalize_output_dir"](str(parent))

    assert result["ok"] is False
    survival = json.loads((parent / "autoplay-campaign-results-unzipped" / "survival-exit-criteria-summary.json").read_text(encoding="utf-8"))
    assert survival["ok"] is False
    assert "drink_water_count_ok" in survival["failed_checks"]
    assert "eat_food_count_ok" in survival["failed_checks"]
    assert "rest_count_ok" in survival["failed_checks"]


def test_bundle_ar_main_wrapper_runs_after_main_with_namespace_args(tmp_path):
    parent = tmp_path / "autoplay-output"
    _seed_output(parent, with_actions=True)

    def main(argv=None):
        return 0

    namespace = _load_bundle_ar_namespace({"main": main})
    result = namespace["main"](argparse.Namespace(output_dir=str(parent)))

    assert result == 0
    assert namespace["BUNDLE_AR_ATEXIT_RESULT"]["ok"] is True
    survival = json.loads((parent / "autoplay-campaign-results-unzipped" / "survival-exit-criteria-summary.json").read_text(encoding="utf-8"))
    assert survival["bundle_ar_survival_autoplay_evidence"] is True


def test_bundle_ar_write_text_wrapper_injects_survival_action(tmp_path):
    _load_bundle_ar_namespace()
    path = tmp_path / "player-action-context.json"

    path.write_text(
        json.dumps({"state": {"needs": {"thirst": 0.85}, "inventory": {"water": 1}}, "candidate_actions": []}),
        encoding="utf-8",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["candidate_actions"][0]["action"] == "drink water"
    assert payload["survival_pressure"]["active"] is True
