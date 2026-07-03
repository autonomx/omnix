from __future__ import annotations

from app.assist_core.hermes_assist_mode import hermes_assist_mode_policy


def test_assist_mode_defaults_to_review_each_step() -> None:
    result = hermes_assist_mode_policy(None)

    assert result["mode"] == "review_each_step"
    assert result["requires_review"] is True
    assert result["execution_allowed"] is True


def test_assist_mode_off_and_suggest_only_block_execution() -> None:
    assert hermes_assist_mode_policy("off")["execution_allowed"] is False
    assert hermes_assist_mode_policy("suggest_only")["blocked_reason"] == "suggest_only"


def test_auto_low_risk_can_skip_review_only_without_checkpoint() -> None:
    assert hermes_assist_mode_policy("auto_low_risk")["requires_review"] is False
    risky = hermes_assist_mode_policy("auto_low_risk", checkpoint_reason="combat_action")
    assert risky["requires_review"] is True


def test_high_risk_still_requires_review() -> None:
    result = hermes_assist_mode_policy("manual_override", high_risk=True)

    assert result["requires_review"] is True
    assert result["execution_allowed"] is False
