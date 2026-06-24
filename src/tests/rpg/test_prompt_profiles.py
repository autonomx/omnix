from __future__ import annotations

import pytest

from app.rpg.prompt_profiles import (
    DEFAULT_RPG_PROMPT_PROFILES,
    default_rpg_prompt_profile_registry,
    resolve_rpg_prompt_profile,
    rpg_prompt_profile_debug_payload,
    validate_rpg_prompt_profile_registry,
)


def test_default_registry_covers_all_prompt_tasks() -> None:
    registry = default_rpg_prompt_profile_registry()

    assert len(registry) == len(DEFAULT_RPG_PROMPT_PROFILES)
    assert validate_rpg_prompt_profile_registry(registry) == ()
    assert registry["intent_classification"].temperature == 0.0
    assert registry["memory_summary"].execution_mode == "background"


def test_resolve_prompt_profile_applies_safe_overrides() -> None:
    profile = resolve_rpg_prompt_profile(
        "narration",
        overrides={"model": "qwen-local", "timeout_seconds": 9.5, "streaming": False},
    )

    assert profile.task == "narration"
    assert profile.model == "qwen-local"
    assert profile.timeout_seconds == 9.5
    assert profile.streaming is False


def test_resolve_prompt_profile_rejects_unknown_override() -> None:
    with pytest.raises(ValueError, match="unknown RPG prompt profile override"):
        resolve_rpg_prompt_profile("narration", overrides={"unknown": "value"})


def test_prompt_profile_debug_payload_is_report_friendly() -> None:
    payload = rpg_prompt_profile_debug_payload("quality_rewrite", latency_ms=123.4, status="completed")

    assert payload["task"] == "quality_rewrite"
    assert payload["profile_id"] == "rpg-quality-rewrite"
    assert payload["latency_ms"] == 123.4
    assert payload["status"] == "completed"


def test_registry_validation_reports_missing_tasks() -> None:
    registry = default_rpg_prompt_profile_registry()
    incomplete = dict(registry)
    incomplete.pop("image_prompt")

    assert validate_rpg_prompt_profile_registry(incomplete) == ("missing:image_prompt",)
