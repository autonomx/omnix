from __future__ import annotations

import json
from pathlib import Path


_PARTS_DIR = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts"
_Q_FRAGMENT = _PARTS_DIR / "zz_bundle_q_1000_turn_preflight_profile.pyfrag"
_S_FRAGMENT = _PARTS_DIR / "zz_bundle_s_live_1000_run_profile.pyfrag"
_AE_FRAGMENT = _PARTS_DIR / "zzzz_bundle_ae_1000_progression_graph_expansion.pyfrag"


def _load_bundle_ae_namespace():
    namespace = {"__name__": "_bundle_ae_1000_progression_graph_expansion_test"}
    for fragment in (_Q_FRAGMENT, _S_FRAGMENT, _AE_FRAGMENT):
        exec(compile(fragment.read_text(encoding="utf-8"), str(fragment), "exec"), namespace, namespace)
    return namespace


def test_bundle_ae_progression_graph_has_1000_turn_capacity_and_unique_edges():
    namespace = _load_bundle_ae_namespace()
    graph = namespace["_bundle_ae_build_1000_progression_graph"]()
    summary = namespace["_bundle_ae_validate_progression_graph"](graph)

    assert graph["format_version"] == "bundle_ae_1000_progression_graph_v1"
    assert graph["target_turns"] == 1000
    assert summary["format_version"] == "bundle_ae_1000_progression_graph_summary_v1"
    assert summary["ok"] is True
    assert summary["progression_graph_ready"] is True
    assert summary["advisory_failures"] == []
    assert summary["checks"]["route_chain_count_ready"] is True
    assert summary["checks"]["objective_edge_count_ready"] is True
    assert summary["checks"]["objective_edge_ids_unique"] is True
    assert summary["checks"]["estimated_turn_capacity_ready"] is True
    assert summary["metrics"]["route_chain_count"] >= 8
    assert summary["metrics"]["objective_edge_count"] >= 72
    assert summary["metrics"]["estimated_turn_capacity"] >= 1000


def test_bundle_ae_progression_graph_covers_required_action_verbs_and_repeat_escape_edges():
    namespace = _load_bundle_ae_namespace()
    graph = namespace["_bundle_ae_build_1000_progression_graph"]()
    summary = namespace["_bundle_ae_validate_progression_graph"](graph)

    for verb in ("ask", "travel", "investigate", "report", "resolve", "restock"):
        assert verb in summary["covered_verbs"]
    assert summary["checks"]["required_verbs_covered"] is True
    assert summary["checks"]["repeat_escape_edges_present"] is True
    assert any(edge.get("repeat_escape") for edge in graph["objective_edges"])
    assert any(edge.get("stage") == "route_check" for edge in graph["objective_edges"])
    assert any(edge.get("stage") == "follow_up" for edge in graph["objective_edges"])
    assert any(edge.get("stage") == "restock" for edge in graph["objective_edges"])


def test_bundle_ae_stale_loop_replacements_are_concrete_and_replace_generic_focus_action():
    namespace = _load_bundle_ae_namespace()
    graph = namespace["_bundle_ae_build_1000_progression_graph"]()
    summary = namespace["_bundle_ae_validate_progression_graph"](graph)

    assert summary["checks"]["stale_loop_replacements_present"] is True
    assert summary["checks"]["stale_loop_replacements_are_concrete"] is True
    generic = "I check in with Garran and focus on the active wagon-road objective."
    replacement = namespace["_bundle_ae_replacement_for_stale_action"](generic, 605)
    assert replacement != generic
    assert "focus on the active" not in replacement.lower()
    assert "active wagon-road objective" not in replacement.lower()
    assert any(word in replacement.lower() for word in ("ask", "travel", "investigate", "report", "restock", "resolve"))
    unchanged = namespace["_bundle_ae_replacement_for_stale_action"]("Ask Bran about the road marker.", 1)
    assert unchanged == "Ask Bran about the road marker."


def test_bundle_ae_patches_preflight_and_live_profile_metadata():
    namespace = _load_bundle_ae_namespace()

    for profile_name in ("_BUNDLE_Q_PROFILE", "_BUNDLE_S_PROFILE"):
        defaults = namespace[profile_name]["defaults"]
        assert defaults["progression_graph_enabled"] is True
        assert defaults["progression_graph_profile"] == "bundle_ae_1000_progression_graph_v1"
        assert defaults["progression_graph_min_capacity"] == 1000
        assert defaults["stale_loop_replacement_enabled"] is True


def test_bundle_ae_writes_graph_and_summary_when_profile_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_ae_namespace()
    original_write_text = namespace["_BUNDLE_AE_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        (tmp_path / "one-thousand-turn-preflight-profile-summary.json").write_text(
            json.dumps({"ok": True, "source": "test"}),
            encoding="utf-8",
        )

        graph_path = tmp_path / "one-thousand-turn-progression-graph.json"
        summary_path = tmp_path / "one-thousand-turn-progression-graph-summary.json"
        assert graph_path.exists()
        assert summary_path.exists()
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert graph["format_version"] == "bundle_ae_1000_progression_graph_v1"
        assert summary["ok"] is True
        assert summary["progression_graph_ready"] is True
        assert summary["metrics"]["estimated_turn_capacity"] >= 1000
        assert summary["recommended_next_step"] == "run_1000_turn_preflight_with_progression_graph"
    finally:
        Path.write_text = original_write_text
