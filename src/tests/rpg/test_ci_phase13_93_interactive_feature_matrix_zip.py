from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests.rpg import interactive_feature_matrix_zip as feature_zip


def _base_result(*, failed: list[str] | None = None) -> dict[str, Any]:
    return {
        "summary": {
            "scenario_count": 1,
            "failed": list(failed or []),
            "performance": {"total_seconds": 1.25},
            "details": {"suite": "phase13.93"},
        },
        "results": [
            {
                "scenario": SimpleNamespace(id="feature-alpha"),
                "result": {"turns": []},
                "validation": {"ok": True},
            }
        ],
    }


def test_phase13_93_feature_matrix_zip_requires_live_provider(capsys) -> None:
    assert feature_zip.main([]) == 2

    output = capsys.readouterr()
    assert "--live-provider" in output.out


def test_phase13_93_feature_matrix_zip_passes_cli_options_and_writes_summary_artifacts(monkeypatch, tmp_path: Path, capsys) -> None:
    selected = [SimpleNamespace(id="feature-alpha")]
    calls: dict[str, Any] = {}

    def fake_select(scenario_ids: list[str]) -> list[Any]:
        calls["scenario_ids"] = list(scenario_ids)
        return selected

    def fake_run_feature_matrix(**kwargs: Any) -> dict[str, Any]:
        calls["run_kwargs"] = dict(kwargs)
        output_root = Path(kwargs["output_root"])
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "matrix.json").write_text("{}", encoding="utf-8")
        return _base_result()

    def fake_zip_matrix_output(output_root: Path, zip_path: Path | None = None) -> Path:
        calls["zip_args"] = {"output_root": output_root, "zip_path": zip_path}
        resolved = Path(zip_path or output_root.with_suffix(".zip"))
        with zipfile.ZipFile(resolved, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output_root).as_posix())
        return resolved

    output_root = tmp_path / "feature-matrix"
    zip_path = tmp_path / "custom-feature-matrix.zip"
    monkeypatch.setattr(feature_zip.feature_matrix, "_select_feature_scenarios", fake_select)
    monkeypatch.setattr(feature_zip.feature_matrix, "run_feature_matrix", fake_run_feature_matrix)
    monkeypatch.setattr(feature_zip.matrix_zip, "zip_matrix_output", fake_zip_matrix_output)

    assert (
        feature_zip.main(
            [
                "--live-provider",
                "--scenario",
                "feature-alpha",
                "--scenario",
                "feature-beta",
                "--output-root",
                str(output_root),
                "--zip-path",
                str(zip_path),
                "--no-live-survival-seed",
                "--no-response-quality-cleanup",
            ]
        )
        == 0
    )

    summary_path = output_root / "interactive-feature-matrix-summary.json"
    performance_path = output_root / "interactive-feature-matrix-performance.json"
    report_path = output_root / "interactive-feature-matrix-report.html"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    output = capsys.readouterr()
    stdout_summary = json.loads(output.out.split("\n[INTERACTIVE-FEATURE-MATRIX-ZIP]", 1)[0])
    assert calls["scenario_ids"] == ["feature-alpha", "feature-beta"]
    assert calls["run_kwargs"] == {
        "scenarios": selected,
        "output_root": output_root,
        "live_provider": True,
        "seed_live_survival": False,
    }
    assert calls["zip_args"] == {"output_root": output_root, "zip_path": zip_path}
    assert summary["zip_path"] == str(zip_path)
    assert stdout_summary["zip_path"] == str(zip_path)
    assert summary["summary_path"] == str(summary_path)
    assert summary["performance_path"] == str(performance_path)
    assert summary["html_report_path"] == str(report_path)
    assert json.loads(performance_path.read_text(encoding="utf-8")) == {"total_seconds": 1.25}
    assert report_path.read_text(encoding="utf-8")
    assert f"[INTERACTIVE-FEATURE-MATRIX-ZIP] {zip_path}" in output.out


def test_phase13_93_feature_matrix_zip_runs_all_cleanup_adapters_and_revalidates_when_changed(
    monkeypatch, tmp_path: Path
) -> None:
    cleanup_names = [
        "response",
        "commerce",
        "travel",
        "memory",
        "equipment",
        "bundle",
        "checkpoint",
    ]
    cleanup_calls: list[str] = []
    calls: dict[str, Any] = {}

    def cleanup_result(name: str, changed_turns: int) -> Any:
        def apply(result: dict[str, Any]) -> dict[str, Any]:
            cleanup_calls.append(name)
            result.setdefault("cleanup_seen", []).append(name)
            return {"changed_turns": changed_turns, "source": name}

        return apply

    def fake_run_feature_matrix(**kwargs: Any) -> dict[str, Any]:
        Path(kwargs["output_root"]).mkdir(parents=True, exist_ok=True)
        return _base_result()

    def fake_revalidate(result: dict[str, Any]) -> dict[str, Any]:
        calls["revalidated"] = True
        result["summary"]["revalidated"] = True
        return result

    def fake_rewrite(result: dict[str, Any], output_root: Path) -> None:
        calls["rewrite"] = {"result": result, "output_root": output_root}

    def fake_zip(output_root: Path, zip_path: Path | None = None) -> Path:
        resolved = Path(zip_path or output_root.with_suffix(".zip"))
        with zipfile.ZipFile(resolved, "w") as archive:
            archive.writestr("placeholder.txt", "ok")
        return resolved

    monkeypatch.setattr(feature_zip.feature_matrix, "_select_feature_scenarios", lambda ids: [SimpleNamespace(id="feature-alpha")])
    monkeypatch.setattr(feature_zip.feature_matrix, "run_feature_matrix", fake_run_feature_matrix)
    monkeypatch.setattr(feature_zip, "apply_response_quality_to_matrix_result", cleanup_result("response", 1))
    monkeypatch.setattr(feature_zip, "apply_commerce_sell_state_to_matrix_result", cleanup_result("commerce", 0))
    monkeypatch.setattr(feature_zip, "apply_travel_state_to_matrix_result", cleanup_result("travel", 0))
    monkeypatch.setattr(feature_zip, "apply_short_session_memory_recall_to_matrix_result", cleanup_result("memory", 0))
    monkeypatch.setattr(feature_zip, "apply_equipment_inventory_to_matrix_result", cleanup_result("equipment", 0))
    monkeypatch.setattr(feature_zip, "apply_interactive_cli_state_bundle_to_matrix_result", cleanup_result("bundle", 0))
    monkeypatch.setattr(feature_zip, "apply_interactive_cli_state_checkpoints_to_matrix_result", cleanup_result("checkpoint", 0))
    monkeypatch.setattr(feature_zip, "_revalidate_after_cleanup", fake_revalidate)
    monkeypatch.setattr(feature_zip.matrix_zip, "_rewrite_matrix_artifacts_after_cleanup", fake_rewrite)
    monkeypatch.setattr(feature_zip.matrix_zip, "zip_matrix_output", fake_zip)

    assert feature_zip.main(["--live-provider", "--output-root", str(tmp_path / "matrix")]) == 0

    assert cleanup_calls == cleanup_names
    assert calls["revalidated"] is True
    assert calls["rewrite"]["output_root"] == tmp_path / "matrix"
    summary = json.loads((tmp_path / "matrix" / "interactive-feature-matrix-summary.json").read_text(encoding="utf-8"))
    assert summary["revalidated"] is True
    assert summary["response_quality_cleanup"] == {"changed_turns": 1, "source": "response"}
    assert summary["interactive_cli_state_checkpoint"] == {"changed_turns": 0, "source": "checkpoint"}


def test_phase13_93_feature_matrix_zip_skips_revalidation_when_cleanup_has_no_changes(monkeypatch, tmp_path: Path) -> None:
    calls = {"revalidated": 0, "rewrite": 0}

    def fake_run_feature_matrix(**kwargs: Any) -> dict[str, Any]:
        Path(kwargs["output_root"]).mkdir(parents=True, exist_ok=True)
        return _base_result()

    def unchanged(_: dict[str, Any]) -> dict[str, Any]:
        return {"changed_turns": 0}

    def fail_revalidate(result: dict[str, Any]) -> dict[str, Any]:
        calls["revalidated"] += 1
        return result

    def fail_rewrite(result: dict[str, Any], output_root: Path) -> None:
        calls["rewrite"] += 1

    monkeypatch.setattr(feature_zip.feature_matrix, "_select_feature_scenarios", lambda ids: [SimpleNamespace(id="feature-alpha")])
    monkeypatch.setattr(feature_zip.feature_matrix, "run_feature_matrix", fake_run_feature_matrix)
    monkeypatch.setattr(feature_zip, "apply_response_quality_to_matrix_result", unchanged)
    monkeypatch.setattr(feature_zip, "apply_commerce_sell_state_to_matrix_result", unchanged)
    monkeypatch.setattr(feature_zip, "apply_travel_state_to_matrix_result", unchanged)
    monkeypatch.setattr(feature_zip, "apply_short_session_memory_recall_to_matrix_result", unchanged)
    monkeypatch.setattr(feature_zip, "apply_equipment_inventory_to_matrix_result", unchanged)
    monkeypatch.setattr(feature_zip, "apply_interactive_cli_state_bundle_to_matrix_result", unchanged)
    monkeypatch.setattr(feature_zip, "apply_interactive_cli_state_checkpoints_to_matrix_result", unchanged)
    monkeypatch.setattr(feature_zip, "_revalidate_after_cleanup", fail_revalidate)
    monkeypatch.setattr(feature_zip.matrix_zip, "_rewrite_matrix_artifacts_after_cleanup", fail_rewrite)
    monkeypatch.setattr(feature_zip.matrix_zip, "zip_matrix_output", lambda output_root, zip_path=None: output_root.with_suffix(".zip"))

    assert feature_zip.main(["--live-provider", "--output-root", str(tmp_path / "matrix")]) == 0

    assert calls == {"revalidated": 0, "rewrite": 0}


def test_phase13_93_feature_matrix_zip_exit_code_tracks_failed_summary(monkeypatch, tmp_path: Path) -> None:
    def fake_run_feature_matrix(**kwargs: Any) -> dict[str, Any]:
        Path(kwargs["output_root"]).mkdir(parents=True, exist_ok=True)
        return _base_result(failed=["feature-alpha"])

    monkeypatch.setattr(feature_zip.feature_matrix, "_select_feature_scenarios", lambda ids: [SimpleNamespace(id="feature-alpha")])
    monkeypatch.setattr(feature_zip.feature_matrix, "run_feature_matrix", fake_run_feature_matrix)
    monkeypatch.setattr(feature_zip.matrix_zip, "zip_matrix_output", lambda output_root, zip_path=None: output_root.with_suffix(".zip"))

    assert (
        feature_zip.main(
            [
                "--live-provider",
                "--output-root",
                str(tmp_path / "matrix"),
                "--no-response-quality-cleanup",
            ]
        )
        == 1
    )


def test_phase13_93_feature_matrix_zip_zip_contains_final_summary_state(monkeypatch, tmp_path: Path) -> None:
    def fake_run_feature_matrix(**kwargs: Any) -> dict[str, Any]:
        output_root = Path(kwargs["output_root"])
        output_root.mkdir(parents=True, exist_ok=True)
        return _base_result()

    def realish_zip(output_root: Path, zip_path: Path | None = None) -> Path:
        resolved = Path(zip_path or output_root.with_suffix(".zip"))
        with zipfile.ZipFile(resolved, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output_root).as_posix())
        return resolved

    output_root = tmp_path / "matrix"
    zip_path = tmp_path / "matrix.zip"
    monkeypatch.setattr(feature_zip.feature_matrix, "_select_feature_scenarios", lambda ids: [SimpleNamespace(id="feature-alpha")])
    monkeypatch.setattr(feature_zip.feature_matrix, "run_feature_matrix", fake_run_feature_matrix)
    monkeypatch.setattr(feature_zip.matrix_zip, "zip_matrix_output", realish_zip)

    assert (
        feature_zip.main(
            [
                "--live-provider",
                "--output-root",
                str(output_root),
                "--zip-path",
                str(zip_path),
                "--no-response-quality-cleanup",
            ]
        )
        == 0
    )

    disk_summary = json.loads((output_root / "interactive-feature-matrix-summary.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(zip_path) as archive:
        zip_summary = json.loads(archive.read("interactive-feature-matrix-summary.json").decode("utf-8"))
        assert "interactive-feature-matrix-performance.json" in set(archive.namelist())
        assert "interactive-feature-matrix-report.html" in set(archive.namelist())
    assert disk_summary["zip_path"] == str(zip_path)
    assert zip_summary["zip_path"] == str(zip_path)
    assert zip_summary["summary_path"] == str(output_root / "interactive-feature-matrix-summary.json")
