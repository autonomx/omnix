from __future__ import annotations

import json
from pathlib import Path

from app.assistant_memory.settings import AssistantMemoryRuntimeSettings
from app.chat import context_budget as context_budget_module
from app.chat import memory_prompt as memory_prompt_module
from app.chat import retention_policy as retention_policy_module
from app.chat.models import ChatSession
from app.gateway import live_chat_companion_context as companion_context
from app.gateway import live_chat_prompt_dependency_stages as dependency_stages


def test_settings_cache_reuses_unchanged_file_and_observes_signature_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    settings_path = tmp_path / "memory-settings.json"
    settings_path.write_text(
        json.dumps({"compaction_enabled": False}),
        encoding="utf-8",
    )
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
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_LOAD_MEMORY_SETTINGS",
        fake_load,
    )

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
                dependency_stages.os.environ.get(
                    "OMNIX_COMPANION_MASTER_ENABLED"
                )
                != "false"
            )
        )

    monkeypatch.setattr(
        dependency_stages.memory_settings_module,
        "default_memory_settings_path",
        lambda: settings_path,
    )
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_LOAD_MEMORY_SETTINGS",
        fake_load,
    )
    monkeypatch.delenv("OMNIX_COMPANION_MASTER_ENABLED", raising=False)

    assert (
        dependency_stages._load_memory_runtime_settings_cached()
        .companion_master_enabled
        is True
    )
    monkeypatch.setenv("OMNIX_COMPANION_MASTER_ENABLED", "false")
    assert (
        dependency_stages._load_memory_runtime_settings_cached()
        .companion_master_enabled
        is False
    )
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
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_LOAD_MEMORY_SETTINGS",
        fake_load,
    )
    monkeypatch.setattr(
        memory_prompt_module,
        "load_memory_runtime_settings",
        dependency_stages._load_memory_runtime_settings_cached,
    )

    assert memory_prompt_module.chat_memory_enabled() is True
    assert memory_prompt_module.chat_memory_enabled() is True
    assert calls == 1


def test_retention_policy_internal_loader_uses_the_signature_cache(
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
        return AssistantMemoryRuntimeSettings(transcript_retention_enabled=True)

    monkeypatch.setattr(
        dependency_stages.memory_settings_module,
        "default_memory_settings_path",
        lambda: settings_path,
    )
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_LOAD_MEMORY_SETTINGS",
        fake_load,
    )
    monkeypatch.setattr(
        retention_policy_module,
        "load_memory_runtime_settings",
        dependency_stages._load_memory_runtime_settings_cached,
    )
    session = ChatSession(
        id="chat:retention-cache",
        title="Retention cache",
        created_at="2026-08-25T00:00:00+00:00",
        updated_at="2026-08-25T00:00:00+00:00",
    )

    assert retention_policy_module.transcript_retention_allowed(session) is True
    assert retention_policy_module.transcript_retention_allowed(session) is True
    assert calls == 1


def test_prompt_budget_internal_loader_uses_the_signature_cache(
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
            memory_token_budget=321,
            history_token_budget=654,
        )

    monkeypatch.setattr(
        dependency_stages.memory_settings_module,
        "default_memory_settings_path",
        lambda: settings_path,
    )
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_LOAD_MEMORY_SETTINGS",
        fake_load,
    )
    monkeypatch.setattr(
        context_budget_module,
        "load_memory_runtime_settings",
        dependency_stages._load_memory_runtime_settings_cached,
    )

    first = context_budget_module.prompt_budget_from_env()
    second = context_budget_module.prompt_budget_from_env()

    assert first.memory_tokens == 321
    assert first.history_tokens == 654
    assert second.memory_tokens == 321
    assert second.history_tokens == 654
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

    monkeypatch.setattr(
        dependency_stages.shared,
        "SETTINGS_FILE",
        str(settings_path),
    )
    monkeypatch.setattr(
        dependency_stages.shared,
        "_settings_load_override",
        None,
    )
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
    assert (
        dependency_stages._get_global_system_prompt_cached()
        == "second, longer prompt"
    )
    assert calls == 2


def test_global_prompt_cache_reuses_override_and_invalidates_after_save(
    monkeypatch,
) -> None:
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    state = {"global_system_prompt": "first"}
    calls = 0
    saved_payloads: list[dict[str, str]] = []

    def fake_get_prompt() -> str:
        nonlocal calls
        calls += 1
        return state["global_system_prompt"]

    def fake_save(payload: dict[str, str]) -> None:
        saved_payloads.append(dict(payload))
        state["global_system_prompt"] = payload["global_system_prompt"]

    monkeypatch.setattr(
        dependency_stages.shared,
        "_settings_load_override",
        object(),
    )
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_GET_GLOBAL_SYSTEM_PROMPT",
        fake_get_prompt,
    )
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_SAVE_SETTINGS",
        fake_save,
    )
    monkeypatch.setenv(
        "OMNIX_LIVE_GLOBAL_PROMPT_CACHE_TTL_SECONDS",
        "60",
    )

    assert dependency_stages._get_global_system_prompt_cached() == "first"
    assert dependency_stages._get_global_system_prompt_cached() == "first"
    assert calls == 1

    dependency_stages._save_settings_and_invalidate(
        {"global_system_prompt": "second"}
    )

    assert saved_payloads == [{"global_system_prompt": "second"}]
    assert dependency_stages._get_global_system_prompt_cached() == "second"
    assert calls == 2


def test_global_prompt_override_cache_expires_after_ttl(
    monkeypatch,
) -> None:
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    values = iter(("first", "second"))
    times = iter((100.0, 102.0))
    monkeypatch.setattr(
        dependency_stages.shared,
        "_settings_load_override",
        object(),
    )
    monkeypatch.setattr(
        dependency_stages,
        "_ORIGINAL_GET_GLOBAL_SYSTEM_PROMPT",
        lambda: next(values),
    )
    monkeypatch.setattr(
        dependency_stages.time,
        "monotonic",
        lambda: next(times),
    )
    monkeypatch.setenv(
        "OMNIX_LIVE_GLOBAL_PROMPT_CACHE_TTL_SECONDS",
        "1",
    )

    assert dependency_stages._get_global_system_prompt_cached() == "first"
    assert dependency_stages._get_global_system_prompt_cached() == "second"


def test_lazy_memory_service_factory_creates_once_on_first_use() -> None:
    calls = 0
    service = object()

    def factory() -> object:
        nonlocal calls
        calls += 1
        return service

    lazy = companion_context._lazy_memory_service_factory(factory)

    assert calls == 0
    assert lazy() is service
    assert lazy() is service
    assert calls == 1
