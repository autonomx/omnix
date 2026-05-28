from __future__ import annotations

from pathlib import Path

_FRAGMENT = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts" / "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_bundle_ar6_turn_input_survival_override.pyfrag"


def _load_ns(extra=None):
    ns = {"__name__": "_bundle_ar6_test"}
    if extra:
        ns.update(extra)
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), ns, ns)
    return ns


def test_bundle_ar6_rewrites_player_input_kwarg_sequence():
    ns = _load_ns()

    args, kwargs, action = ns["_bundle_ar6_patch_call"]("execute_turn", (), {"player_input": "secure records"})
    assert kwargs["player_input"] == "drink water from my waterskin"
    assert action == "drink water from my waterskin"

    args, kwargs, action = ns["_bundle_ar6_patch_call"]("execute_turn", (), {"player_input": "secure records"})
    assert kwargs["player_input"] == "eat rations from my pack"

    args, kwargs, action = ns["_bundle_ar6_patch_call"]("execute_turn", (), {"player_input": "secure records"})
    assert kwargs["player_input"] == "rest at camp until recovered"


def test_bundle_ar6_wrapper_overrides_fake_turn_function():
    def execute_turn(session, player_input=None):
        return {"player_input": player_input}

    ns = _load_ns({"execute_turn": execute_turn})
    ns["_bundle_ar6_patch_runtime_functions"]()

    result = ns["execute_turn"]("s1", player_input="secure records")

    assert result["player_input"] == "drink water from my waterskin"
    assert ns["BUNDLE_AR6_OVERRIDDEN_TURN_INPUTS"][-1]["category"] == "drink_water"


def test_bundle_ar6_positional_string_override():
    ns = _load_ns()

    args, kwargs, action = ns["_bundle_ar6_patch_call"]("run_turn", ("session-id", "secure records"), {})

    assert args[1] == "drink water from my waterskin"
    assert action == "drink water from my waterskin"


def test_bundle_ar6_summary_counts_overrides(tmp_path):
    ns = _load_ns()
    parent = tmp_path / "run"
    unzipped = parent / "autoplay-campaign-results-unzipped"
    unzipped.mkdir(parents=True)
    ns["BUNDLE_AR6_LAST_OUTPUT_DIR"] = str(parent)
    ns["BUNDLE_AR6_OVERRIDDEN_TURN_INPUTS"] = [
        {"action": "drink water from my waterskin", "category": "drink_water"},
        {"action": "eat rations from my pack", "category": "eat_food"},
        {"action": "rest at camp until recovered", "category": "rest"},
    ]

    summary = ns["_bundle_ar6_summary"](str(parent))

    assert summary["ok"] is True
    assert (unzipped / "survival-turn-input-override-summary.json").exists()
