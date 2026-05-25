from __future__ import annotations

import json
from pathlib import Path


_PARTS_DIR = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts"
_AE_FRAGMENT = _PARTS_DIR / "zzzz_bundle_ae_1000_progression_graph_expansion.pyfrag"
_AI_FRAGMENT = _PARTS_DIR / "zzzzzzzzz_bundle_ai_progression_graph_runtime_edge_selection.pyfrag"


def _load_bundle_ai_namespace(extra_globals=None):
    namespace = {"__name__": "_bundle_ai_progression_graph_runtime_edge_selection_test"}
    if extra_globals:
        namespace.update(extra_globals)
    for fragment in (_AE_FRAGMENT, _AI_FRAGMENT):
        exec(compile(fragment.read_text(encoding="utf-8"), str(fragment), "exec"), namespace, namespace)
    return namespace


def test_bundle_ai_selects_rotating_concrete_progression_edge_actions():
    namespace = _load_bundle_ai_namespace()

    actions = [namespace["_bundle_ai_select_progression_edge_action"](turn) for turn in range(10)]

    assert len(set(actions)) >= 6
    assert all("which exact wagon-road clue is unresolved" not in action.lower() for action in actions)
    assert all("focus on the active wagon-road objective" not in action.lower() for action in actions)
    assert any(action.startswith("Ask ") for action in actions)
    assert any(action.startswith("Travel ") for action in actions)
    assert any(action.startswith("Investigate ") for action in actions)
    assert any(action.startswith("Report ") for action in actions)


def test_bundle_ai_repairs_static_bad_fallback_actions_in_nested_artifact_payload():
    namespace = _load_bundle_ai_namespace()
    payload = {
        "turns": [
            {
                "turn_index": 19,
                "player_action": "Ask Garran which exact wagon-road clue is unresolved, what changed since the last attempt, and which named route node to visit next.",
                "nested": {
                    "canonical_turn_action": "I check in with Garran and focus on the active wagon-road objective."
                },
            },
            {
                "turn_index": 20,
                "player_action": "I ask Bran who last saw the witness near the tavern.",
            },
        ]
    }

    repaired, changed = namespace["_bundle_ai_repair_static_actions"](payload)

    assert changed == 2
    first = repaired["turns"][0]
    assert first["player_action"] != payload["turns"][0]["player_action"]
    assert "which exact wagon-road clue is unresolved" not in first["player_action"].lower()
    assert "focus on the active wagon-road objective" not in first["nested"]["canonical_turn_action"].lower()
    assert repaired["turns"][1]["player_action"] == "I ask Bran who last saw the witness near the tavern."
    assert "bundle_ai_runtime_edge_repairs" in first


def test_bundle_ai_repair_json_artifact_rewrites_bad_static_actions(tmp_path):
    namespace = _load_bundle_ai_namespace()
    artifact = tmp_path / "turn-action-consistency-summary.json"
    # Use the original writer so this fixture is not auto-repaired by Bundle AI's
    # Path.write_text wrapper before the direct repair helper is exercised.
    namespace["_BUNDLE_AI_ORIGINAL_PATH_WRITE_TEXT"](
        artifact,
        json.dumps(
            {
                "examples": [
                    {
                        "turn_index": 19,
                        "player_action": "Ask Garran which exact wagon-road clue is unresolved, what changed since the last attempt, and which named route node to visit next.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    changed = namespace["_bundle_ai_repair_json_artifact"](artifact)
    repaired = json.loads(artifact.read_text(encoding="utf-8"))

    assert changed == 1
    action = repaired["examples"][0]["player_action"]
    assert "which exact wagon-road clue is unresolved" not in action.lower()
    assert action


def test_bundle_ai_write_text_wrapper_auto_repairs_named_artifacts(tmp_path):
    namespace = _load_bundle_ai_namespace()
    artifact = tmp_path / "turn-action-consistency-summary.json"

    artifact.write_text(
        json.dumps(
            {
                "examples": [
                    {
                        "turn_index": 19,
                        "player_action": "Ask Garran which exact wagon-road clue is unresolved, what changed since the last attempt, and which named route node to visit next.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repaired = json.loads(artifact.read_text(encoding="utf-8"))

    action = repaired["examples"][0]["player_action"]
    assert "which exact wagon-road clue is unresolved" not in action.lower()
    assert "bundle_ai_runtime_edge_repairs" in repaired["examples"][0]


def test_bundle_ai_wraps_stale_fallback_returning_functions():
    def fallback_func(turn_index=19):
        return {
            "turn_index": turn_index,
            "player_action": "Ask Garran which exact wagon-road clue is unresolved, what changed since the last attempt, and which named route node to visit next.",
        }

    namespace = _load_bundle_ai_namespace(extra_globals={"fallback_func": fallback_func})

    result = namespace["fallback_func"](19)
    assert "which exact wagon-road clue is unresolved" not in result["player_action"].lower()
    assert "fallback_func" in namespace["BUNDLE_AI_RUNTIME_EDGE_WRAPPED_FUNCTIONS"]


def test_bundle_ai_readiness_truth_blocks_1000_when_density_repair_or_preflight_fail(tmp_path):
    namespace = _load_bundle_ai_namespace()
    (tmp_path / "one-thousand-turn-readiness-aggregator-summary.json").write_text(
        json.dumps({"ok": True, "ready_for_1000_turn_preflight": True, "ready_for_live_1000_turn_run": True, "failing_required_gates": []}),
        encoding="utf-8",
    )
    (tmp_path / "content-exhaustion-forecast-summary.json").write_text(
        json.dumps({"ok": False, "unique_node_density": 0.18, "graph_progression_density": 0.18}),
        encoding="utf-8",
    )
    (tmp_path / "dialogue-repair-quality-summary.json").write_text(
        json.dumps({"ok": True, "repair_rate": 0.91}),
        encoding="utf-8",
    )
    (tmp_path / "one-thousand-turn-preflight-result-summary.json").write_text(
        json.dumps({"ok": False, "promote_to_live_1000_turn_run": False}),
        encoding="utf-8",
    )

    truth = namespace["_bundle_ai_write_truth_summary_if_possible"](tmp_path)
    aggregator = json.loads((tmp_path / "one-thousand-turn-readiness-aggregator-summary.json").read_text(encoding="utf-8"))

    assert truth["ok"] is False
    assert truth["ready_for_1000_turn_preflight"] is False
    assert truth["ready_for_live_1000_turn_run"] is False
    assert "unique_node_density_ok" in truth["truth_blocking_gates"]
    assert "graph_progression_density_ok" in truth["truth_blocking_gates"]
    assert "dialogue_repair_rate_ok" in truth["truth_blocking_gates"]
    assert "preflight_result_ok_or_not_present" in truth["truth_blocking_gates"]
    assert aggregator["ok"] is False
    assert aggregator["ready_for_1000_turn_preflight"] is False
    assert aggregator["ready_for_live_1000_turn_run"] is False
    assert aggregator["bundle_ai_truth_overrides_applied"] is True


def test_bundle_ai_readiness_truth_allows_1000_when_truth_gates_pass(tmp_path):
    namespace = _load_bundle_ai_namespace()
    (tmp_path / "content-exhaustion-forecast-summary.json").write_text(
        json.dumps({"ok": True, "unique_node_density": 0.55, "graph_progression_density": 0.60}),
        encoding="utf-8",
    )
    (tmp_path / "dialogue-repair-quality-summary.json").write_text(
        json.dumps({"ok": True, "repair_rate": 0.10}),
        encoding="utf-8",
    )

    truth = namespace["_bundle_ai_readiness_truth"](tmp_path)

    assert truth["ok"] is True
    assert truth["ready_for_1000_turn_preflight"] is True
    assert truth["truth_blocking_gates"] == []
    assert truth["recommended_next_step"] == "run_1000_turn_preflight"


def test_bundle_ai_patches_q_s_profile_metadata_when_available():
    namespace = _load_bundle_ai_namespace(
        extra_globals={
            "_BUNDLE_Q_PROFILE": {"defaults": {}},
            "_BUNDLE_S_PROFILE": {"defaults": {}},
        }
    )

    for profile_name in ("_BUNDLE_Q_PROFILE", "_BUNDLE_S_PROFILE"):
        defaults = namespace[profile_name]["defaults"]
        assert defaults["runtime_progression_edge_selection"] is True
        assert defaults["readiness_truth_required"] is True
        assert defaults["max_dialogue_repair_rate"] == 0.25
        assert defaults["min_unique_node_density"] == 0.35
        assert defaults["min_graph_progression_density"] == 0.35
