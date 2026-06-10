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


def test_phase13_51_known_feature_gap_downgrades_expectation_failure_without_runtime_error():
    scenario = next(
        item
        for item in feature_matrix.default_feature_matrix_scenarios()
        if item.scenario_id == "equipment_inventory_probe"
    )
    classification = feature_matrix._classify_feature_matrix_results(
        [
            {
                "scenario": scenario,
                "result": {"summary": {"completed_turns": len(scenario.commands), "error_count": 0}},
                "validation": {
                    "ok": False,
                    "scenario_id": scenario.scenario_id,
                    "failures": ["turn 1: inventory wording missing"],
                },
            }
        ]
    )

    assert classification["hard_failures"] == []
    assert classification["feature_gaps"][0]["scenario_id"] == "equipment_inventory_probe"
    assert classification["results"][0]["validation"]["ok"] is True
    assert classification["results"][0]["validation"]["feature_gap"] is True
    assert classification["results"][0]["validation"]["feature_gap_failures"] == [
        "turn 1: inventory wording missing"
    ]


def test_phase13_51_known_feature_gap_still_fails_on_runtime_error():
    scenario = next(
        item
        for item in feature_matrix.default_feature_matrix_scenarios()
        if item.scenario_id == "travel_round_trip_route"
    )
    classification = feature_matrix._classify_feature_matrix_results(
        [
            {
                "scenario": scenario,
                "result": {"summary": {"completed_turns": len(scenario.commands), "error_count": 1}},
                "validation": {
                    "ok": False,
                    "scenario_id": scenario.scenario_id,
                    "failures": ["runtime error"],
                },
            }
        ]
    )

    assert classification["feature_gaps"] == []
    assert classification["hard_failures"][0]["scenario_id"] == "travel_round_trip_route"


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
        "feature_gaps": [],
        "feature_gap_count": 0,
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


def test_phase13_53_feature_zip_revalidates_after_response_quality_cleanup():
    scenario = next(
        item
        for item in feature_matrix.default_feature_matrix_scenarios()
        if item.scenario_id == "shop_sell_attempt"
    )
    result = {
        "summary": {
            "format_version": feature_matrix.FEATURE_MATRIX_VERSION,
            "matrix_kind": "extended_feature_matrix",
            "scenario_count": 1,
            "passed": 0,
            "failed": [
                {
                    "ok": False,
                    "scenario_id": "shop_sell_attempt",
                    "failures": ["turn 1: stale failure"],
                }
            ],
            "feature_gaps": [
                {
                    "scenario_id": "shop_sell_attempt",
                    "failures": ["turn 1: stale failure"],
                }
            ],
            "feature_gap_count": 1,
            "performance": {},
            "details": {},
        },
        "results": [
            {
                "scenario": scenario,
                "result": {
                    "summary": {"completed_turns": 3, "error_count": 0},
                    "turns": [
                        {
                            "turn_index": 1,
                            "player_input": "Bran, can I sell you one ration?",
                            "raw_narration": "Bran treats the request as a trade question, not a survival action.",
                            "narration_preview": "Bran treats the request as a trade question, not a survival action.",
                            "raw_npc": {"speaker": "Bran", "line": "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."},
                            "raw_result": {"narration": "Bran treats the request as a trade question, not a survival action.", "npc": {"speaker": "Bran", "line": "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."}},
                            "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"target_npc": "Bran", "requested_terms": ["sell", "ration", "Bran"]}},
                        },
                        {
                            "turn_index": 2,
                            "player_input": "How much copper would you give me for a ration?",
                            "raw_narration": "Bran treats the request as a trade question, not a survival action.",
                            "narration_preview": "Bran treats the request as a trade question, not a survival action.",
                            "raw_npc": {"speaker": "Bran", "line": "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."},
                            "raw_result": {"narration": "Bran treats the request as a trade question, not a survival action.", "npc": {"speaker": "Bran", "line": "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."}},
                            "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"target_npc": "Bran", "requested_terms": ["sell", "ration", "Bran", "copper"]}},
                        },
                        {
                            "turn_index": 3,
                            "player_input": "I sell one ration to Bran.",
                            "raw_narration": "Bran treats the request as a trade question, not a survival action.",
                            "narration_preview": "Bran treats the request as a trade question, not a survival action.",
                            "raw_npc": {"speaker": "Bran", "line": "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."},
                            "raw_result": {"narration": "Bran treats the request as a trade question, not a survival action.", "npc": {"speaker": "Bran", "line": "I can't buy that ration from you yet; selling provisions is not set up in the current trade state."}},
                            "interactive_cli_intent_diagnostics": {"provider_called": True, "final_classification": {"target_npc": "Bran", "requested_terms": ["sell", "ration", "Bran"]}},
                        },
                    ],
                },
                "validation": {"ok": False, "scenario_id": "shop_sell_attempt", "failures": ["turn 1: stale failure"]},
            }
        ],
    }

    revalidated = feature_zip._revalidate_after_cleanup(result)

    assert revalidated["summary"]["failed"] == []
    assert revalidated["summary"]["feature_gaps"] == []
    assert revalidated["summary"]["feature_gap_count"] == 0
    assert revalidated["summary"]["passed"] == 1
    assert revalidated["results"][0]["validation"]["ok"] is True
