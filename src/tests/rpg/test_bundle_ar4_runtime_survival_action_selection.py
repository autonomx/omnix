from __future__ import annotations

import json
from pathlib import Path

_FRAGMENT = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts" / "zzzzzzzzzzzzzzzzzzzzzzzzzzzzz_bundle_ar4_runtime_survival_action_selection.pyfrag"


def _load_ns(extra=None):
    ns = {"__name__": "_bundle_ar4_test"}
    if extra:
        ns.update(extra)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), ns, ns)
    return ns


def test_bundle_ar4_patches_string_dict_and_list_results():
    ns = _load_ns()
    patch = ns["_bundle_ar4_patch_payload"]
    action = "drink water from my waterskin"

    assert patch("secure records", action) == action
    obj = patch({"selected_action": "secure records", "candidate_actions": [{"action": "ask Bran"}]}, action)
    assert obj["selected_action"] == action
    assert obj["candidate_actions"][0]["action"] == action
    rows = patch([{"action": "ask Bran"}], action)
    assert rows[0]["action"] == action


def test_bundle_ar4_runtime_wrapper_rewrites_fake_selector_result():
    def choose_player_action():
        return {"selected_action": "secure_red_lantern_records", "candidate_actions": [{"action": "secure_red_lantern_records"}]}

    ns = _load_ns({"choose_player_action": choose_player_action})
    ns["BUNDLE_AR4_LAST_OUTPUT_DIR"] = ""

    ns["_bundle_ar4_patch_runtime_functions"]()
    result = ns["choose_player_action"]()

    assert result["selected_action"] == "drink water from my waterskin"
    assert result["candidate_actions"][0]["action"] == "drink water from my waterskin"
    emitted = ns["BUNDLE_AR4_EMITTED_SURVIVAL_ACTIONS"]
    assert emitted[-1]["category"] == "drink_water"


def test_bundle_ar4_emitted_counts_advance_sequence():
    ns = _load_ns()
    ns["BUNDLE_AR4_EMITTED_SURVIVAL_ACTIONS"] = [
        {"action": "drink water from my waterskin", "category": "drink_water"},
        {"action": "eat rations from my pack", "category": "eat_food"},
    ]
    assert ns["_bundle_ar4_next_action"]() == "rest at camp until recovered"


def test_bundle_ar4_summary_writes_runtime_selection_file(tmp_path):
    ns = _load_ns()
    parent = tmp_path / "run"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    ns["BUNDLE_AR4_LAST_OUTPUT_DIR"] = str(parent)
    ns["BUNDLE_AR4_EMITTED_SURVIVAL_ACTIONS"] = [
        {"action": "drink water from my waterskin", "category": "drink_water", "function": "choose_player_action"}
    ]

    summary = ns["_bundle_ar4_summary_for_output"](str(parent))

    assert summary["emitted_action_count"] == 1
    payload = json.loads((unzipped / "survival-runtime-action-selection-summary.json").read_text(encoding="utf-8"))
    assert payload["emitted_action_count"] == 1
    assert payload["next_action"] == "eat rations from my pack"
