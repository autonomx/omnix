from __future__ import annotations

import json
from pathlib import Path

from app.assistant_memory.settings import AssistantMemoryRuntimeSettings
from app.gateway import live_chat_prompt_dependency_stages as dependency_stages


def test_settings_cache_reuses_unchanged_file_and_observes_signature_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    settings_path = tmp_path / "memory-settings.json"
    settings_path.write_text(json.dumps({"compaction_enabled": False}), encoding="utf-8")
    calls = 0

    def fake_load() -> AssistantMemoryRuntimeSettings:
        nonlocal calls
        calls += 1
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        return AssistantMemoryRuntimeSettings.model_validate(payload)

    monkeypatch.setattr(
        dependency_stages.memory_settings_module,
        "default_memory_settings_path",
        lambda: settings_path,
    )
    monkeypatch.setattr(dependency_stages, "_ORIGINAL_LOAD_MEMORY_SETTINGS", fake_load)

    first = dependency_stages._load_memory_runtime_settings_cached()
    second = dependency_stages._load_memory_runtime_settings_cached()

    assert first.compaction_enabled is False
    assert second.compaction_enabled is False
    assert first is not second
    assert calls == 1

    settings_path.write_text(json.dumps({"compaction_enabled": True, "retention_days": 30}), encoding="utf-8")
    third = dependency_stages._load_memory_runtime_settings_cached()

    assert third.compaction_enabled is True
    assert calls == 2


def test_settings_cache_key_observes_environment_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    settings_path = tmp_path / "memory-settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    calls = 0

    def fake_load() -> AssistantMemoryRuntimeSettings:
        nonlocal calls
        calls += 1
        return AssistantMemoryRuntimeSettings(
            companion_master_enabled=(
                dependency_stages.os.environ.get("OMNIX_COMPANION_MASTER_ENABLED") != "false"
            )
        )

    monkeypatch.setattr(
        dependency_stages.memory_settings_module,
        "default_memory_settings_path",
        lambda: settings_path,
    )
    monkeypatch.setattr(dependency_stages, "_ORIGINAL_LOAD_MEMORY_SETTINGS", fake_load)
    monkeypatch.delenv("OMNIX_COMPANION_MASTER_ENABLED", raising=False)

    assert dependency_stages._load_memory_runtime_settings_cached().companion_master_enabled is True
    monkeypatch.setenv("OMNIX_COMPANION_MASTER_ENABLED", "false")
    assert dependency_stages._load_memory_runtime_settings_cached().companion_master_enabled is False
    assert calls == 2
