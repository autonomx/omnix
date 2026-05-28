from __future__ import annotations

import json
from pathlib import Path

_FRAGMENT = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts" / "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_bundle_ar5_strict_survival_real_action_sources.pyfrag"


def _load_ns():
    ns = {"__name__": "_bundle_ar5_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), ns, ns)
    return ns


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_bundle_ar5_ignores_generated_survival_summary_text(tmp_path):
    ns = _load_ns()
    root = tmp_path / "run"
    root.mkdir()
    _write_json(root / "survival-runtime-action-selection-summary.json", {"counts": {"drink_water_count": 10, "eat_food_count": 10, "rest_count": 10}, "next_action": "drink water from my waterskin"})
    _write_json(root / "survival-exit-criteria-summary.json", {"ok": True, "drink_water_count": 10, "eat_food_count": 10, "rest_count": 10})

    result = ns["_bundle_ar5_patch_survival_outputs"](root)

    assert result["ok"] is False
    patched = json.loads((root / "survival-exit-criteria-summary.json").read_text(encoding="utf-8"))
    assert patched["ok"] is False
    assert patched["drink_water_count"] == 0
    assert patched["eat_food_count"] == 0
    assert "survival-runtime-action-selection-summary.json" not in patched["metric_source_files"]


def test_bundle_ar5_accepts_real_console_player_actions(tmp_path):
    ns = _load_ns()
    root = tmp_path / "run"
    root.mkdir()
    (root / "console-log.txt").write_text(
        "[2026] PLAYER: drink water from my waterskin\n"
        "[2026] PLAYER: eat rations from my pack\n"
        "[2026] PLAYER: rest at camp until recovered\n",
        encoding="utf-8",
    )
    _write_json(root / "survival-exit-criteria-summary.json", {"ok": False})

    result = ns["_bundle_ar5_patch_survival_outputs"](root)

    assert result["ok"] is True
    patched = json.loads((root / "survival-exit-criteria-summary.json").read_text(encoding="utf-8"))
    assert patched["ok"] is True
    assert patched["drink_water_count"] == 1
    assert patched["eat_food_count"] == 1
    assert patched["rest_count"] == 1
    assert patched["metric_source_files"] == ["console-log.txt"]


def test_bundle_ar5_finalize_parent_and_unzipped(tmp_path):
    ns = _load_ns()
    parent = tmp_path / "run"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    for directory in (parent, unzipped):
        directory.mkdir(parents=True)
        (directory / "console-log.txt").write_text(
            "PLAYER: drink water from my waterskin\nPLAYER: eat rations from my pack\nPLAYER: rest at camp until recovered\n",
            encoding="utf-8",
        )
        _write_json(directory / "survival-exit-criteria-summary.json", {"ok": False})

    result = ns["_bundle_ar5_finalize_output_dir"](str(parent))

    assert result["ok"] is True
    assert result["result_count"] == 2
    assert (unzipped / "survival-real-action-source-audit-summary.json").exists()
