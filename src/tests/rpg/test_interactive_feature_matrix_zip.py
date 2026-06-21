from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from tests.rpg import interactive_feature_matrix_zip as fmzip


def _patch_cleanups(monkeypatch: Any, changed_turns: int = 0) -> None:
    cleanup_result = {"changed_turns": changed_turns}
    monkeypatch.setattr(fmzip, "apply_response_quality_to_matrix_result", lambda result: cleanup_result)
    monkeypatch.setattr(fmzip, "apply_commerce_sell_state_to_matrix_result", lambda result: {"changed_turns": 0})
    monkeypatch.setattr(fmzip, "apply_travel_state_to_matrix_result", lambda result: {"changed_turns": 0})
    monkeypatch.setattr(fmzip, "apply_short_session_memory_recall_to_matrix_result", lambda result: {"changed_turns": 0})
    monkeypatch.setattr(fmzip, "apply_equipment_inventory_to_matrix_result", lambda result: {"changed_turns": 0})
    monkeypatch.setattr(fmzip, "apply_interactive_cli_state_bundle_to_matrix_result", lambda result: {"changed_turns": 0})
    monkeypatch.setattr(fmzip, "apply_interactive_cli_state_checkpoints_to_matrix_result", lambda result: {"changed_turns": 0})


def test_live_provider_flag_is_required(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(
        fmzip.feature_matrix,
        "run_feature_matrix",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    exit_code = fmzip.main([])

    assert exit_code == 2
    assert "--live-provider" in capsys.readouterr().out


def test_live_provider_run_uses_seed_cleanup_and_zip(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    result = {"summary": {"failed": [], "scenario_count": 1}, "results": []}
    output_root = tmp_path / "matrix"
    zip_path = tmp_path / "matrix.zip"

    monkeypatch.setattr(fmzip.feature_matrix, "_select_feature_scenarios", lambda scenario_ids: ["shop_buy"])

    def fake_run_feature_matrix(**kwargs: Any) -> dict[str, Any]:
        calls["run"] = kwargs
        return result

    monkeypatch.setattr(fmzip.feature_matrix, "run_feature_matrix", fake_run_feature_matrix)
    _patch_cleanups(monkeypatch)
    monkeypatch.setattr(fmzip.matrix_zip, "zip_matrix_output", lambda root, requested: requested)
    written_summaries: list[dict[str, Any]] = []
    monkeypatch.setattr(
        fmzip,
        "_write_feature_matrix_summary_artifacts",
        lambda summary_result, root: written_summaries.append(deepcopy(summary_result["summary"])),
    )

    exit_code = fmzip.main(
        [
            "--live-provider",
            "--scenario",
            "shop_buy",
            "--output-root",
            str(output_root),
            "--zip-path",
            str(zip_path),
        ]
    )

    assert exit_code == 0
    assert calls["run"] == {
        "scenarios": ["shop_buy"],
        "output_root": output_root,
        "live_provider": True,
        "seed_live_survival": True,
    }
    assert result["summary"]["zip_path"] == str(zip_path)
    assert result["summary"]["response_quality_cleanup"] == {"changed_turns": 0}
    assert written_summaries[-1]["zip_path"] == str(zip_path)


def test_live_provider_flags_disable_seed_and_cleanup(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    result = {"summary": {"failed": [], "scenario_count": 0}, "results": []}

    monkeypatch.setattr(fmzip.feature_matrix, "_select_feature_scenarios", lambda scenario_ids: [])

    def fake_run_feature_matrix(**kwargs: Any) -> dict[str, Any]:
        calls["run"] = kwargs
        return result

    monkeypatch.setattr(fmzip.feature_matrix, "run_feature_matrix", fake_run_feature_matrix)
    monkeypatch.setattr(
        fmzip,
        "apply_response_quality_to_matrix_result",
        lambda result: (_ for _ in ()).throw(AssertionError("cleanup disabled")),
    )
    monkeypatch.setattr(fmzip.matrix_zip, "zip_matrix_output", lambda root, requested: requested)
    monkeypatch.setattr(fmzip, "_write_feature_matrix_summary_artifacts", lambda result, root: None)

    exit_code = fmzip.main(
        [
            "--live-provider",
            "--no-live-survival-seed",
            "--no-response-quality-cleanup",
            "--output-root",
            str(tmp_path / "matrix"),
        ]
    )

    assert exit_code == 0
    assert calls["run"]["live_provider"] is True
    assert calls["run"]["seed_live_survival"] is False
    assert "response_quality_cleanup" not in result["summary"]
