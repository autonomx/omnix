import json
import zipfile
from pathlib import Path

from tests.rpg import interactive_feature_matrix as feature_matrix
from tests.rpg import interactive_feature_matrix_zip as feature_zip


def test_phase13_51_feature_matrix_defines_extended_scenarios():
    scenarios = feature_matrix.default_feature_matrix_scenarios()
    scenario_ids = {scenario.scenario_id for scenario in scenarios}

    assert len(scenarios) >= 6
    assert "inn_room_purchase_flow" in scenario_ids
    assert "shop_sell_attempt" in scenario_ids
    assert "travel_round_trip_route" in scenario_ids
    assert "npc_memory_recall_probe" in scenario_ids
    assert "equipment_inventory_probe" in scenario_ids
    assert "backed_quest_acceptance_probe" in scenario_ids
    assert all(scenario.commands for scenario in scenarios)
    assert all(scenario.expectations for scenario in scenarios)


def test_phase13_51_feature_matrix_scenario_selection():
    selected = feature_matrix._select_feature_scenarios(["travel_round_trip_route"])

    assert [scenario.scenario_id for scenario in selected] == ["travel_round_trip_route"]


def test_phase13_51_feature_zip_wrapper_requires_live_provider(capsys):
    exit_code = feature_zip.main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--live-provider" in captured.out


def test_phase13_51_feature_zip_wrapper_writes_archive(monkeypatch, tmp_path: Path):
    scenario = feature_matrix.default_feature_matrix_scenarios()[0]
    summary = {
        "format_version": feature_matrix.FEATURE_MATRIX_VERSION,
        "matrix_kind": "extended_feature_matrix",
        "scenario_count": 1,
        "passed": 1,
        "failed": [],
        "output_root": str(tmp_path),
        "performance": {},
        "details": {},
    }
    result = {"summary": summary, "results": []}

    def fake_select(names):
        return [scenario]

    def fake_run_feature_matrix(*, scenarios, output_root, live_provider, seed_live_survival):
        assert scenarios == [scenario]
        assert live_provider is True
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "marker.txt").write_text("ok", encoding="utf-8")
        return result

    monkeypatch.setattr(feature_matrix, "_select_feature_scenarios", fake_select)
    monkeypatch.setattr(feature_matrix, "run_feature_matrix", fake_run_feature_matrix)

    exit_code = feature_zip.main(["--live-provider", "--scenario", scenario.scenario_id, "--output-root", str(tmp_path), "--no-response-quality-cleanup"])

    assert exit_code == 0
    zip_path = tmp_path.with_suffix(".zip")
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        assert "marker.txt" in archive.namelist()
    loaded = json.loads((tmp_path / "interactive-feature-matrix-summary.json").read_text(encoding="utf-8"))
    assert loaded["zip_path"] == str(zip_path)
