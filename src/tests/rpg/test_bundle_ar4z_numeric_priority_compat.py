from __future__ import annotations

from pathlib import Path

_FRAGMENT_AR4 = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts" / "zzzzzzzzzzzzzzzzzzzzzzzzzzzzz_bundle_ar4_runtime_survival_action_selection.pyfrag"
_FRAGMENT_AR4Z = Path(__file__).resolve().parent / "autoplay_llm_campaign_parts" / "zzzzzzzzzzzzzzzzzzzzzzzzzzzz_bundle_ar4z_numeric_priority_compat.pyfrag"


def _load_ns():
    ns = {"__name__": "_bundle_ar4z_test"}
    exec(compile(_FRAGMENT_AR4.read_text(encoding="utf-8"), str(_FRAGMENT_AR4), "exec"), ns, ns)
    exec(compile(_FRAGMENT_AR4Z.read_text(encoding="utf-8"), str(_FRAGMENT_AR4Z), "exec"), ns, ns)
    return ns


def test_bundle_ar4z_action_entry_priority_is_int_castable():
    ns = _load_ns()
    entry = ns["_bundle_ar4_action_entry"]("drink water from my waterskin")
    assert int(entry["priority"]) == 100000
    assert entry["priority_reason"] == "runtime_selected_until_survival_exit_criteria_has_real_evidence"


def test_bundle_ar4z_patched_payload_can_be_sorted_by_strategy_priority():
    ns = _load_ns()
    patched = ns["_bundle_ar4_patch_payload"]({"candidate_actions": [{"action": "ask Bran", "priority": 0}]}, "drink water from my waterskin")
    priorities = [int(action.get("priority") or 0) for action in patched["candidate_actions"]]
    assert priorities[0] == 100000
    assert priorities[1] == 0
