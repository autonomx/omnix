from __future__ import annotations

from app.rpg.session.fast_combat_narration_skip import (
    force_install_fast_combat_narration_skip_for_tests,
)
from app.rpg.session import runtime


def test_ce2121_fast_combat_narration_skip_bypasses_provider(monkeypatch):
    force_install_fast_combat_narration_skip_for_tests()

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
    assert "hit" in result["narration"]


def test_ce2121_non_fast_combat_narration_still_calls_original_provider(monkeypatch):
    force_install_fast_combat_narration_skip_for_tests()
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

    monkeypatch.setattr(runtime, "combat_contract_requires_llm", fake_requires_llm)
    monkeypatch.setattr(runtime, "generate_combat_narration_sync", fake_provider)

    result = runtime._apply_combat_narration_if_needed(
        {},
        combat_result={"reason": "hit", "action_type": "attack"},
        combat_state={"active": True},
    )

    assert called["value"] is True
    assert result.get("combat_narration_skipped_for_fast_mode") is not True


def test_ce2121_fast_combat_narration_skip_installs_idempotently():
    first = force_install_fast_combat_narration_skip_for_tests()
    second = force_install_fast_combat_narration_skip_for_tests()

    assert first is True
    assert second is True
