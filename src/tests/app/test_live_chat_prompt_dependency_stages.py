from __future__ import annotations

import json
from pathlib import Path

from app.assistant_memory.settings import AssistantMemoryRuntimeSettings
from app.chat import memory_prompt as memory_prompt_module
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

    settings_path.write_text(
        json.dumps({"compaction_enabled": True, "retention_days": 30}),
        encoding="utf-8",
    )
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


def test_memory_prompt_internal_loader_uses_the_signature_cache(
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
        return AssistantMemoryRuntimeSettings(curated_memory_enabled=True)

    monkeypatch.setattr(
        dependency_stages.memory_settings_module,
        "default_memory_settings_path",
        lambda: settings_path,
    )
    monkeypatch.setattr(dependency_stages, "_ORIGINAL_LOAD_MEMORY_SETTINGS", fake_load)
    monkeypatch.setattr(
        memory_prompt_module,
        "load_memory_runtime_settings",
        dependency_stages._load_memory_runtime_settings_cached,
    )

    assert memory_prompt_module.chat_memory_enabled() is True
    assert memory_prompt_module.chat_memory_enabled() is True
    assert calls == 1


def test_global_prompt_cache_reuses_settings_file_and_observes_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"global_system_prompt": "first prompt"}),
        encoding="utf-8",
    )
    calls = 0

    def fake_get_prompt() -> str:
        nonlocal calls
        calls += 1
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        return str(payload["global_system_prompt"])

    monkeypatch.setattr(dependency_stages.shared, "SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr(dependency_stages.shared, "_settings_load_override", None)
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_GET_GLOBAL_SYSTEM_PROMPT",
        fake_get_prompt,
    )

    assert dependency_stages._get_global_system_prompt_cached() == "first prompt"
    assert dependency_stages._get_global_system_prompt_cached() == "first prompt"
    assert calls == 1

    settings_path.write_text(
        json.dumps({"global_system_prompt": "second, longer prompt"}),
        encoding="utf-8",
    )
    assert dependency_stages._get_global_system_prompt_cached() == "second, longer prompt"
    assert calls == 2


def test_global_prompt_cache_bypasses_unversioned_loader_override(
    monkeypatch,
) -> None:
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    values = iter(("first", "second"))
    monkeypatch.setattr(dependency_stages.shared, "_settings_load_override", object())
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_GET_GLOBAL_SYSTEM_PROMPT",
        lambda: next(values),
    )

    assert dependency_stages._get_global_system_prompt_cached() == "first"
    assert dependency_stages._get_global_system_prompt_cached() == "second"
