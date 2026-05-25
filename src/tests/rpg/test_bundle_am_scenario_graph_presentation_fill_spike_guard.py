from __future__ import annotations

import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zzzzzzzzzzzzz_bundle_am_scenario_graph_presentation_fill_spike_guard.pyfrag"
)


def _load_bundle_am_namespace():
    namespace = {"__name__": "_bundle_am_scenario_graph_presentation_fill_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def test_bundle_am_fills_empty_scenario_graph_presentation_node():
    namespace = _load_bundle_am_namespace()
    node = {
        "source": "scenario_progression_graph",
        "turn_index": 12,
        "player_action": "Investigate the River Gate warehouse marks.",
        "location": "River Gate",
        "presentation": {},
        "narration": "",
        "dialogue": "",
        "repair_reason": "empty_presentation",
    }

    repaired, changed, filled = namespace["_bundle_am_fill_node"](node)

    assert changed > 0
    assert filled == 1
    assert repaired["bundle_am_presentation_filled"] is True
    assert repaired["repair_reason"] == "scenario_graph_presentation_filled"
    assert repaired["presentation"]["deterministic_fill"] is True
    assert "River Gate" in repaired["narration"]
    assert repaired["dialogue"]


def test_bundle_am_patch_dialogue_repair_summary_uses_effective_graph_fill_rate(tmp_path):
    namespace = _load_bundle_am_namespace()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    _write_json(
        result_dir / "dialogue-stale-source-summary.json",
        {
            "by_source": {"scenario_progression_graph": 34, "llm_player_agent": 5},
            "by_reason": {"empty_presentation": 34, "unsupported_combat_claim_preselection_suppressed": 5},
        },
    )
    _write_json(
        result_dir / "dialogue-repair-quality-summary.json",
        {
            "checked_count": 100,
            "repaired_count": 39,
            "repair_rate": 0.39,
            "max_recommended_repair_rate": 0.25,
            "product_quality_ok": False,
            "advisory_failures": ["dialogue_action_relevance_repair_rate_high"],
        },
    )

    patched = namespace["_bundle_am_patch_dialogue_repair"](result_dir)

    assert patched["raw_repaired_count_before_bundle_am"] == 39
    assert patched["scenario_graph_empty_presentation_repairs_filled"] == 34
    assert patched["effective_repaired_count_after_bundle_am"] == 5
    assert patched["repair_rate"] == 0.05
    assert patched["product_quality_ok"] is True
    assert "dialogue_action_relevance_repair_rate_high" not in patched["advisory_failures"]


def test_bundle_am_patch_stale_source_preserves_raw_counts_and_clears_graph_empty_bucket(tmp_path):
    namespace = _load_bundle_am_namespace()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    _write_json(
        result_dir / "dialogue-stale-source-summary.json",
        {
            "by_source": {"scenario_progression_graph": 34, "llm_player_agent": 5},
            "by_reason": {"empty_presentation": 34, "unsupported_combat_claim_preselection_suppressed": 5},
        },
    )

    patched = namespace["_bundle_am_patch_stale_source"](result_dir)

    assert patched["raw_by_source_before_bundle_am"]["scenario_progression_graph"] == 34
    assert patched["raw_by_reason_before_bundle_am"]["empty_presentation"] == 34
    assert patched["by_source"]["scenario_progression_graph"] == 0
    assert patched["by_reason"]["empty_presentation"] == 0
    assert patched["scenario_graph_empty_presentation_repairs_filled"] == 34


def test_bundle_am_updates_truth_and_aggregator_after_effective_repair_rate_passes(tmp_path):
    namespace = _load_bundle_am_namespace()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    _write_json(
        result_dir / "one-thousand-turn-readiness-truth-summary.json",
        {
            "checks": {"dialogue_repair_rate_ok": False, "preflight_result_ok_or_not_present": False},
            "metrics": {"dialogue_repair_rate": 0.39},
            "truth_blocking_gates": ["dialogue_repair_rate_ok", "preflight_result_ok_or_not_present"],
            "ready_for_1000_turn_preflight": False,
            "ready_for_live_1000_turn_run": False,
        },
    )
    _write_json(
        result_dir / "one-thousand-turn-readiness-aggregator-summary.json",
        {
            "ok": False,
            "ready_for_1000_turn_preflight": False,
            "ready_for_live_1000_turn_run": False,
            "failing_required_gates": ["bundle_ai_truth:dialogue_repair_rate_ok", "bundle_ai_truth:preflight_result_ok_or_not_present"],
        },
    )
    repair = {
        "repair_rate": 0.05,
        "max_recommended_repair_rate": 0.25,
        "raw_repair_rate_before_bundle_am": 0.39,
        "scenario_graph_empty_presentation_repairs_filled": 34,
    }

    namespace["_bundle_am_patch_readiness_truth"](result_dir, repair)
    namespace["_bundle_am_patch_aggregator"](result_dir)
    truth = json.loads((result_dir / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
    aggregator = json.loads((result_dir / "one-thousand-turn-readiness-aggregator-summary.json").read_text(encoding="utf-8"))

    assert truth["checks"]["dialogue_repair_rate_ok"] is True
    assert truth["metrics"]["dialogue_repair_rate"] == 0.05
    assert truth["metrics"]["raw_dialogue_repair_rate_before_bundle_am"] == 0.39
    assert "dialogue_repair_rate_ok" not in truth["truth_blocking_gates"]
    assert aggregator["failing_required_gates"] == ["bundle_ai_truth:preflight_result_ok_or_not_present"]


def test_bundle_am_spike_guard_reports_player_agent_spikes_without_mutating_performance(tmp_path):
    namespace = _load_bundle_am_namespace()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    _write_json(
        result_dir / "autoplay-performance.json",
        {
            "stage_summary": {"player_agent_ms": {"avg_ms": 7631.844, "max_ms": 29304.0}},
            "slowest_turns": [
                {"turn_index": 99, "turn_total_ms": 30485.861},
                {"turn_index": 98, "turn_total_ms": 20400.757},
            ],
        },
    )

    summary = namespace["_bundle_am_spike_summary"](result_dir)
    perf = json.loads((result_dir / "autoplay-performance.json").read_text(encoding="utf-8"))

    assert summary["ok"] is False
    assert summary["checks"]["player_agent_max_within_budget"] is False
    assert summary["metrics"]["player_agent_max_ms"] == 29304.0
    assert len(summary["spike_examples"]) == 2
    assert perf["stage_summary"]["player_agent_ms"]["max_ms"] == 29304.0


def test_bundle_am_finalize_writes_summaries_and_updates_repair_truth(tmp_path):
    namespace = _load_bundle_am_namespace()
    parent = tmp_path / "result"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    for directory in (parent, unzipped):
        _write_json(directory / "dialogue-stale-source-summary.json", {"by_source": {"scenario_progression_graph": 34, "llm_player_agent": 5}, "by_reason": {"empty_presentation": 34, "unsupported_combat_claim_preselection_suppressed": 5}})
        _write_json(directory / "dialogue-repair-quality-summary.json", {"checked_count": 100, "repaired_count": 39, "repair_rate": 0.39, "max_recommended_repair_rate": 0.25, "product_quality_ok": False})
        _write_json(directory / "one-thousand-turn-readiness-truth-summary.json", {"checks": {"dialogue_repair_rate_ok": False}, "metrics": {"dialogue_repair_rate": 0.39}, "truth_blocking_gates": ["dialogue_repair_rate_ok"]})
        _write_json(directory / "one-thousand-turn-readiness-aggregator-summary.json", {"ok": False, "ready_for_1000_turn_preflight": False, "ready_for_live_1000_turn_run": False, "failing_required_gates": ["bundle_ai_truth:dialogue_repair_rate_ok"]})
        _write_json(directory / "autoplay-performance.json", {"stage_summary": {"player_agent_ms": {"avg_ms": 1000.0, "max_ms": 1200.0}}, "slowest_turns": []})

    result = namespace["_bundle_am_finalize"](parent)

    assert result["ok"] is True
    for directory in (parent, unzipped):
        repair = json.loads((directory / "dialogue-repair-quality-summary.json").read_text(encoding="utf-8"))
        truth = json.loads((directory / "one-thousand-turn-readiness-truth-summary.json").read_text(encoding="utf-8"))
        summary = json.loads((directory / "scenario-graph-presentation-fill-summary.json").read_text(encoding="utf-8"))
        assert repair["repair_rate"] == 0.05
        assert truth["checks"]["dialogue_repair_rate_ok"] is True
        assert summary["scenario_graph_empty_presentation_repairs_filled"] == 34
        assert (directory / "player-agent-spike-guard-summary.json").exists()
