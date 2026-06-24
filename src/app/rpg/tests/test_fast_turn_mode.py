from __future__ import annotations

from app.rpg.session.fast_turn_mode import (
    FAST_TURN_SETTINGS_VERSION,
    fast_turn_enabled,
    fast_turn_performance_override,
    resolve_fast_turn_settings,
)


def test_fast_turn_mode_defaults_off(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RPG_FAST_TURN_MODE", raising=False)

    settings = resolve_fast_turn_settings()

    assert settings.format_version == FAST_TURN_SETTINGS_VERSION
    assert settings.enabled is False
    assert settings.mode == "standard"
    assert settings.max_context_tokens == 3000
    assert settings.max_output_tokens == 180


def test_fast_turn_mode_can_be_enabled_by_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RPG_FAST_TURN_MODE", "1")

    assert fast_turn_enabled() is True
    assert resolve_fast_turn_settings().enabled is True


def test_fast_turn_override_clamps_budgets() -> None:
    settings = resolve_fast_turn_settings(
        {
            "fast_turn_mode": True,
            "max_context_tokens": 99,
            "max_output_tokens": 9999,
            "narration_mode": "deterministic",
        }
    )

    assert settings.enabled is True
    assert settings.max_context_tokens == 500
    assert settings.max_output_tokens == 600
    assert settings.narration_mode == "deterministic"


def test_fast_turn_performance_override_preserves_existing_values() -> None:
    override = fast_turn_performance_override(
        {
            "fast_turn_mode": True,
            "enable_live_narration_llm": True,
            "max_output_tokens": 90,
        }
    )

    assert override["fast_turn_mode"] is True
    assert override["enable_live_narration_llm"] is True
    assert override["max_output_tokens"] == 90
    assert override["fast_turn_settings"]["enabled"] is True
