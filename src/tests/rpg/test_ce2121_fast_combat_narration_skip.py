from __future__ import annotations

from app.rpg.session.fast_combat_narration_skip import fast_combat_narration_scope
from app.rpg.session import runtime


def test_ce2121_fast_combat_narration_skip_bypasses_provider(monkeypatch):
    def fail_provider(*args, **kwargs):  # pragma: no cover - asserted by absence of raise
        raise AssertionError("combat narration provider should not be called in fast mode")

    monkeypatch.setattr(runtime, "generate_combat_narration_sync", fail_provider)

    payload = {
        "fast_direct_runtime": True,
        "skip_sync_combat_narration": True,
        "fast_direct_source": "ce212_fast_direct_runtime_budget_v1",
    }
    result = runtime._apply_combat_narration_if_needed(
        payload,
        combat_result={"reason": "hit", "action_type": "attack"},
        combat_state={"active": True, "skip_sync_combat_narration": True},
    )

    assert result["combat_narration_skipped_for_fast_mode"] is True
    assert result["combat_narration_skip_source"] == "ce212_fast_combat_narration_skip_v1"
    assert result["llm_called"] is False
    assert result["llm_purpose"] == "deterministic_combat_fast_summary"
    assert result["combat_narration_payload"]["source"] == "deterministic_combat_fast_summary"
    assert result["narration_payload"]["source"] == "deterministic_combat_fast_summary"
    assert result["structured_narration"]["source"] == "deterministic_combat_fast_summary"
    assert "hit" in result["narration"].lower()


def test_ce2122_matrix_shaped_fast_direct_marker_bypasses_provider(monkeypatch):
    def fail_provider(*args, **kwargs):  # pragma: no cover - asserted by absence of raise
        raise AssertionError("combat narration provider should not be called for matrix fast-direct marker")

    monkeypatch.setattr(runtime, "generate_combat_narration_sync", fail_provider)

    payload = {
        "turn_contract": {
            "action": {
                "action_type": "combat",
                "metadata": {
                    "fast_direct_runtime": True,
                    "source": "ce211_fast_direct_runtime_budget_v1",
                },
            }
        }
    }
    result = runtime._apply_combat_narration_if_needed(
        payload,
        combat_result={"reason": "hit", "action_type": "attack"},
        combat_state={"active": True},
    )

    assert result["combat_narration_skipped_for_fast_mode"] is True
    assert result["combat_narration_payload"]["source"] == "deterministic_combat_fast_summary"
    assert result["narration_payload"]["source"] == "deterministic_combat_fast_summary"
    assert result["llm_called"] is False


def test_pr01_fast_combat_damage_delta_replaces_stale_no_injury_summary(monkeypatch):
    def fail_provider(*args, **kwargs):  # pragma: no cover - asserted by absence of raise
        raise AssertionError("combat narration provider should not be called for damage delta fast mode")

    monkeypatch.setattr(runtime, "generate_combat_narration_sync", fail_provider)

    result = runtime._apply_combat_narration_if_needed(
        {
            "fast_direct_runtime": True,
            "skip_sync_combat_narration": True,
            "narration": "The confrontation remains tense, but no injury is resolved.",
            "result": {"narration": "The confrontation remains tense, but no injury is resolved."},
        },
        combat_result={
            "reason": "hit",
            "action_type": "attack",
            "damage_applied": 1,
            "target_hp_before": 4,
            "target_hp_after": 3,
            "target_name": "bandit",
        },
        combat_state={"active": True, "enemy_hp": 3, "skip_sync_combat_narration": True},
    )

    assert result["combat_delta_contract"]["damage_applied"] == 1
    assert result["combat_delta_contract"]["target_hp_before"] == 4
    assert result["combat_delta_contract"]["target_hp_after"] == 3
    assert result["combat_narration_payload"]["combat_delta"]["damage_applied"] == 1
    assert "1 damage" in result["narration"]
    assert "3 HP remaining" in result["narration"]
    assert "no injury is resolved" not in result["narration"]
    assert "1 damage" in result["result"]["narration"]


def test_pr01_fast_combat_defeat_summary_uses_delta_contract(monkeypatch):
    def fail_provider(*args, **kwargs):  # pragma: no cover - asserted by absence of raise
        raise AssertionError("combat narration provider should not be called for defeat fast mode")

    monkeypatch.setattr(runtime, "generate_combat_narration_sync", fail_provider)

    result = runtime._apply_combat_narration_if_needed(
        {
            "fast_direct_runtime": True,
            "skip_sync_combat_narration": True,
            "narration": "The confrontation remains tense, but no injury is resolved.",
        },
        combat_result={
            "reason": "hit",
            "action_type": "attack",
            "damage_applied": 1,
            "target_hp_before": 1,
            "target_hp_after": 0,
            "target_name": "bandit",
            "defeated": True,
            "combat_ended": True,
        },
        combat_state={"active": False, "enemy_hp": 0, "defeated": True, "skip_sync_combat_narration": True},
    )

    assert result["combat_delta_contract"]["defeated"] is True
    assert result["combat_delta_contract"]["combat_ended"] is True
    assert "1 damage" in result["narration"]
    assert "defeat" in result["narration"].lower()
    assert "no injury is resolved" not in result["narration"]


def test_ce2124_fast_combat_action_detection_and_flag_injection():
    import app.rpg.session.fast_combat_narration_skip as hook

    action = {
        "action_type": "combat",
        "target_id": "enemy:road_bandit",
        "target_name": "road bandit",
        "metadata": {"fast_direct_runtime": True, "source": "ce212_fast_direct_runtime_budget_v1"},
    }

    assert hook._action_requests_fast_combat_skip(action, {"fast_turn_mode": True}) is True

    args, kwargs = hook._with_fast_combat_flags(
        (),
        {"action": action, "performance_override": {"fast_turn_mode": True}},
        action=action,
        performance_override={"fast_turn_mode": True},
    )

    assert args == ()
    assert kwargs["performance_override"]["skip_sync_combat_narration"] is True
    assert kwargs["performance_override"]["fast_direct_runtime"] is True
    assert kwargs["action"]["metadata"]["skip_sync_combat_narration"] is True
    assert kwargs["action"]["metadata"]["fast_direct_runtime"] is True


def test_ce2121_non_fast_combat_narration_still_calls_original_provider(monkeypatch):
    from app.rpg.session import runtime_part01_legacy
    called = {"value": False}

    def fake_requires_llm(combat_result):
        return True

    def fake_provider(*args, **kwargs):
        called["value"] = True
        return {
            "llm_called": False,
            "accepted": False,
            "combat_narration_contract": {},
            "combat_narration_validation": {"ok": False},
            "payload": {},
        }

    monkeypatch.setattr(runtime_part01_legacy, "combat_contract_requires_llm", fake_requires_llm)
    monkeypatch.setattr(runtime_part01_legacy, "generate_combat_narration_sync", fake_provider)

    result = runtime._apply_combat_narration_if_needed(
        {},
        combat_result={"reason": "hit", "action_type": "attack"},
        combat_state={"active": True},
    )

    assert called["value"] is True
    assert result.get("combat_narration_skipped_for_fast_mode") is not True


def test_ce2125_fast_combat_scope_injects_flags_for_one_turn():
    action = {"action_type": "combat", "metadata": {"source": "ce212_fast_direct_runtime_budget_v1"}}
    with fast_combat_narration_scope(action, {"fast_turn_mode": True}) as (scoped_action, performance):
        assert performance["skip_sync_combat_narration"] is True
        assert performance["fast_direct_runtime"] is True
        assert scoped_action["metadata"]["skip_sync_combat_narration"] is True
        assert scoped_action["metadata"]["fast_direct_runtime"] is True
