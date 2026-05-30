from __future__ import annotations

import inspect

from app.rpg.session.state_claim_audit import audit_final_result_hard_state_claims
from tests.rpg.manual import turn_execution


def test_pr0_manual_harness_selects_interactive_runtime_by_default(monkeypatch):
    traces = []

    def record_trace(event: str, **kwargs):
        traces.append((event, kwargs))

    monkeypatch.setattr(turn_execution, "record_manual_harness_trace", record_trace)

    apply_turn = turn_execution._get_apply_turn()

    assert apply_turn.__module__ == "app.rpg.session.interactive_first_call_runtime"
    selected = [payload for event, payload in traces if event == "manual_harness_selected_apply_turn"]
    assert selected
    assert selected[-1]["module_name"] == "app.rpg.session.interactive_first_call_runtime"
    assert selected[-1]["selection_kind"] == "interactive_first_call_runtime"
    assert selected[-1]["interactive_first_call_enabled"] is True


def test_pr0_manual_harness_has_no_fast_direct_gameplay_shortcut():
    source = inspect.getsource(turn_execution)

    forbidden_fragments = (
        "_get_canonical_apply_turn",
        "_fast_direct_action",
        "_attach_fast_direct_diagnostics",
        "fast_direct_canonical_runtime",
        "action=fast_direct_action",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_pr0_fast_direct_detection_lives_in_interactive_runtime():
    from app.rpg.session import interactive_first_call_runtime

    action = interactive_first_call_runtime._fast_direct_action(
        "I attack the bandit.",
        {"fast_turn_mode": True},
    )

    assert action["action_type"] == "combat"
    assert action["target_id"] == "enemy:road_bandit"
    assert action["metadata"]["fast_direct_runtime"] is True
    assert action["metadata"]["skip_sync_combat_narration"] is True


def test_pr0_stateful_first_call_visible_response_is_ignored_for_stateful_runtime_contract():
    from app.rpg.session import interactive_first_call_runtime

    result = interactive_first_call_runtime._apply_stateful_narration_contract(
        {
            "narration": "Runtime resolved the real action.",
            "result": {"narration_status": "queued"},
        },
        narration_mode="deferred",
        action_advisory={
            "stateful": True,
            "visible_response": {"narration": "The LLM says you get 999 gold."},
            "first_call_grounding_diagnostics": {"source": "test"},
        },
        semantic_advisory={},
        selection={"reason": "stateful_runtime_required"},
    )

    contract = result["stateful_runtime_narration_contract"]
    assert contract["stateful_runtime_authoritative"] is True
    assert contract["first_call_may_resolve_state"] is False
    assert contract["runtime_resolved_before_narration"] is True
    assert contract["narration_may_mutate_state"] is False
    assert contract["first_call_visible_response_ignored_for_stateful"] is True
    assert "999 gold" not in result.get("narration", "")


def test_pr0_hard_state_claim_audit_reports_combat_defeat_contradiction():
    audit = audit_final_result_hard_state_claims(
        {
            "narration": "The bandit is defeated and falls dead.",
            "runtime_state": {"combat_state": {"active": True, "enemy_hp": 2, "defeated": False}},
        }
    )

    assert audit["source"] == "phase0_hard_state_claim_audit_v1"
    assert audit["ok"] is False
    assert "narration_claims_defeat_but_combat_state_does_not" in audit["critical"]


def test_pr0_hard_state_claim_audit_passes_grounded_combat_defeat():
    audit = audit_final_result_hard_state_claims(
        {
            "narration": "The bandit is defeated.",
            "runtime_state": {"combat_state": {"active": False, "enemy_hp": 0, "defeated": True}},
        }
    )

    assert audit["ok"] is True
    assert audit["critical"] == []
