from __future__ import annotations

import inspect

from tests.rpg.manual import turn_execution


def test_ce213_manual_harness_prefers_interactive_first_call_runtime(monkeypatch):
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


def test_ce213_manual_harness_no_longer_owns_fast_direct_gameplay_routing():
    source = inspect.getsource(turn_execution)

    assert "_get_canonical_apply_turn" not in source
    assert "_fast_direct_action" not in source
    assert "_attach_fast_direct_diagnostics" not in source
    assert "fast_direct_canonical_runtime" not in source
    assert "action=fast_direct_action" not in source


def test_ce213_fast_direct_detection_lives_in_app_runtime_wrapper():
    from app.rpg.session import interactive_first_call_runtime

    action = interactive_first_call_runtime._fast_direct_action(
        "I attack the bandit.",
        {"fast_turn_mode": True},
    )

    assert action["action_type"] == "combat"
    assert action["target_id"] == "enemy:road_bandit"
    assert action["metadata"]["fast_direct_runtime"] is True
    assert action["metadata"]["skip_sync_combat_narration"] is True
