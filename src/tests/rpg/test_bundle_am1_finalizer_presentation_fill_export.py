from __future__ import annotations

import json
from pathlib import Path


_PARTS_DIR = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts"
_AM_FRAGMENT = _PARTS_DIR / "zzzzzzzzzzzzz_bundle_am_scenario_graph_presentation_fill_spike_guard.pyfrag"
_AM1_FRAGMENT = _PARTS_DIR / "zzzzzzzzzzzzzz_bundle_am1_finalizer_presentation_fill_export.pyfrag"


def _load_bundle_am1_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_am1_finalizer_presentation_fill_export_test"}
    if extra_globals:
        namespace.update(extra_globals)
    for fragment in (_AM_FRAGMENT, _AM1_FRAGMENT):
        exec(compile(fragment.read_text(encoding="utf-8"), str(fragment), "exec"), namespace, namespace)
    return namespace


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def test_bundle_am1_mirrors_parent_am_summaries_into_unzipped(tmp_path):
    namespace = _load_bundle_am1_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(parent / "scenario-graph-presentation-fill-summary.json", {"ok": True, "source": "parent_am", "filled_node_count": 34})
    _write_json(parent / "player-agent-spike-guard-summary.json", {"ok": True, "source": "parent_spike"})

    result = namespace["_bundle_am1_mirror_am_outputs"](parent)

    assert result["ok"] is True
    assert result["presentation_summary_present"] is True
    assert result["spike_summary_present"] is True
    mirrored = json.loads((unzipped / "scenario-graph-presentation-fill-summary.json").read_text(encoding="utf-8"))
    spike = json.loads((unzipped / "player-agent-spike-guard-summary.json").read_text(encoding="utf-8"))
    assert mirrored["source"] == "parent_am"
    assert spike["source"] == "parent_spike"
    assert (unzipped / "scenario-graph-presentation-fill-export-summary.json").exists()
    assert (parent / "scenario-graph-presentation-fill-export-summary.json").exists()


def test_bundle_am1_finalize_root_runs_am_and_exports_to_unzipped(tmp_path):
    namespace = _load_bundle_am1_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    for directory in (parent, unzipped):
        _write_json(directory / "dialogue-stale-source-summary.json", {"by_source": {"scenario_progression_graph": 34, "llm_player_agent": 5}, "by_reason": {"empty_presentation": 34, "unsupported_combat_claim_preselection_suppressed": 5}})
        _write_json(directory / "dialogue-repair-quality-summary.json", {"checked_count": 100, "repaired_count": 39, "repair_rate": 0.39, "max_recommended_repair_rate": 0.25, "product_quality_ok": False})
        _write_json(directory / "one-thousand-turn-readiness-truth-summary.json", {"checks": {"dialogue_repair_rate_ok": False}, "metrics": {"dialogue_repair_rate": 0.39}, "truth_blocking_gates": ["dialogue_repair_rate_ok"]})
        _write_json(directory / "one-thousand-turn-readiness-aggregator-summary.json", {"ok": False, "ready_for_1000_turn_preflight": False, "ready_for_live_1000_turn_run": False, "failing_required_gates": ["bundle_ai_truth:dialogue_repair_rate_ok"]})
        _write_json(directory / "autoplay-performance.json", {"stage_summary": {"player_agent_ms": {"avg_ms": 1000.0, "max_ms": 1200.0}}, "slowest_turns": []})

    result = namespace["_bundle_am1_finalize_root"](parent)

    assert result["ok"] is True
    assert (unzipped / "scenario-graph-presentation-fill-summary.json").exists()
    assert (unzipped / "player-agent-spike-guard-summary.json").exists()
    repair = json.loads((unzipped / "dialogue-repair-quality-summary.json").read_text(encoding="utf-8"))
    assert repair["repair_rate"] == 0.05
    export = json.loads((unzipped / "scenario-graph-presentation-fill-export-summary.json").read_text(encoding="utf-8"))
    assert export["presentation_summary_present"] is True


def test_bundle_am1_manifest_finalizer_runs_pre_and_post_finalize(tmp_path):
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(parent / "scenario-graph-presentation-fill-summary.json", {"ok": True, "source": "parent_am"})

    def hard_finalizer():
        return {"ok": True, "hard_finalized": True}

    namespace = _load_bundle_am1_namespace(
        {
            "_manifest_hard_finalize_latest": hard_finalizer,
            "RESULT_DIR_FOR_TEST": str(parent),
        }
    )

    result = namespace["_manifest_hard_finalize_latest"]()

    assert result["ok"] is True
    assert namespace["BUNDLE_AM1_PREFINALIZE_RESULT"]["root_count"] >= 1
    assert namespace["BUNDLE_AM1_POSTFINALIZE_RESULT"]["root_count"] >= 1
    assert (unzipped / "scenario-graph-presentation-fill-summary.json").exists()


def test_bundle_am1_write_text_wrapper_mirrors_existing_parent_summary(tmp_path):
    _load_bundle_am1_namespace()
    parent = tmp_path / "autoplay-output"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    _write_json(parent / "scenario-graph-presentation-fill-summary.json", {"ok": True, "source": "parent_am"})

    (parent / "artifact-manifest-digest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    assert (unzipped / "scenario-graph-presentation-fill-summary.json").exists()
    mirrored = json.loads((unzipped / "scenario-graph-presentation-fill-summary.json").read_text(encoding="utf-8"))
    assert mirrored["source"] == "parent_am"
