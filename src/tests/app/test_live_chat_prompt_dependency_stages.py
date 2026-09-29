from __future__ import annotations

from app.assistant_memory.settings import AssistantMemoryRuntimeSettings
from app.chat import context_budget as context_budget_module
from app.chat import memory_prompt as memory_prompt_module
from app.chat import retention_policy as retention_policy_module
from app.chat.models import ChatSession
from app.gateway import live_chat_companion_context as companion_context
from app.gateway import live_chat_prompt_dependency_stages as dependency_stages
from app.providers import service as provider_service


def _use_test_settings(monkeypatch, loader):
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    monkeypatch.setattr(dependency_stages, "_ORIGINAL_LOAD_MEMORY_SETTINGS", loader)
    monkeypatch.setattr(
        dependency_stages,
        "_settings_cache_key",
        lambda: ("test-settings-service",),
    )


def test_settings_cache_reuses_service_value_and_invalidates_after_update(monkeypatch):
    state = {"settings": AssistantMemoryRuntimeSettings(compaction_enabled=False)}
    calls = 0

    def fake_load() -> AssistantMemoryRuntimeSettings:
        nonlocal calls
        calls += 1
        return state["settings"]

    _use_test_settings(monkeypatch, fake_load)
    first = dependency_stages._load_memory_runtime_settings_cached()
    second = dependency_stages._load_memory_runtime_settings_cached()
    assert first.compaction_enabled is False
    assert second.compaction_enabled is False
    assert first is not second
    assert calls == 1

    state["settings"] = AssistantMemoryRuntimeSettings(
        compaction_enabled=True,
        retention_days=30,
    )
    dependency_stages._invalidate_memory_settings_cache()
    third = dependency_stages._load_memory_runtime_settings_cached()
    assert third.compaction_enabled is True
    assert calls == 2


def test_settings_cache_key_observes_environment_overrides(monkeypatch):
    calls = 0

    def fake_load() -> AssistantMemoryRuntimeSettings:
        nonlocal calls
        calls += 1
        return AssistantMemoryRuntimeSettings(
            companion_master_enabled=(
                dependency_stages.environment().get(
                    "OMNIX_COMPANION_MASTER_ENABLED"
                )
                != "false"
            )
        )

    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    monkeypatch.setattr(dependency_stages, "_ORIGINAL_LOAD_MEMORY_SETTINGS", fake_load)
    monkeypatch.delenv("OMNIX_COMPANION_MASTER_ENABLED", raising=False)
    assert dependency_stages._load_memory_runtime_settings_cached().companion_master_enabled
    monkeypatch.setenv("OMNIX_COMPANION_MASTER_ENABLED", "false")
    assert not dependency_stages._load_memory_runtime_settings_cached().companion_master_enabled
    assert calls == 2


def test_memory_prompt_loader_uses_settings_service_cache(monkeypatch):
    calls = 0

    def fake_load() -> AssistantMemoryRuntimeSettings:
        nonlocal calls
        calls += 1
        return AssistantMemoryRuntimeSettings(curated_memory_enabled=True)

    _use_test_settings(monkeypatch, fake_load)
    monkeypatch.setattr(
        memory_prompt_module,
        "load_memory_runtime_settings",
        dependency_stages._load_memory_runtime_settings_cached,
    )
    assert memory_prompt_module.chat_memory_enabled() is True
    assert memory_prompt_module.chat_memory_enabled() is True
    assert calls == 1


def test_retention_and_prompt_budget_use_settings_service_cache(monkeypatch):
    calls = 0

    def fake_load() -> AssistantMemoryRuntimeSettings:
        nonlocal calls
        calls += 1
        return AssistantMemoryRuntimeSettings(
            transcript_retention_enabled=True,
            memory_token_budget=321,
            history_token_budget=654,
        )

    _use_test_settings(monkeypatch, fake_load)
    monkeypatch.setattr(
        retention_policy_module,
        "load_memory_runtime_settings",
        dependency_stages._load_memory_runtime_settings_cached,
    )
    monkeypatch.setattr(
        context_budget_module,
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
    first = context_budget_module.prompt_budget_from_env()
    second = context_budget_module.prompt_budget_from_env()
    assert first.memory_tokens == second.memory_tokens == 321
    assert first.history_tokens == second.history_tokens == 654
    assert calls == 1


def test_global_prompt_cache_invalidates_after_settings_update(monkeypatch):
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    value = ["first prompt"]
    calls = 0
    callbacks = []

    class SettingsService:
        def subscribe(self, key, callback):
            assert key == "global_system_prompt"
            callbacks.append(callback)

    settings_service = SettingsService()

    def fake_get_prompt() -> str:
        nonlocal calls
        calls += 1
        return value[0]

    monkeypatch.setattr(provider_service, "current_settings_service", lambda: settings_service)
    monkeypatch.setattr(provider_service, "load_settings", lambda: {"global_system_prompt": fake_get_prompt()})
    assert provider_service.get_global_system_prompt() == "first prompt"
    assert provider_service.get_global_system_prompt() == "first prompt"
    assert calls == 1

    value[0] = "updated prompt"
    for callback in callbacks:
        callback("global_system_prompt", value[0])
    assert provider_service.get_global_system_prompt() == "updated prompt"
    assert calls == 2


def test_global_prompt_cache_expires_after_ttl(monkeypatch):
    dependency_stages._reset_live_prompt_dependency_state_for_tests()
    values = iter(("first", "second"))
    times = iter((100.0, 100.0, 102.0))
    monkeypatch.setattr(provider_service, "current_settings_service", lambda: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(provider_service, "load_settings", lambda: {"global_system_prompt": next(values)})
    monkeypatch.setattr(provider_service, "_global_prompt_ttl_seconds", lambda: 1.0)
    monkeypatch.setattr(provider_service.time, "monotonic", lambda: next(times))
    monkeypatch.setenv("OMNIX_LIVE_GLOBAL_PROMPT_CACHE_TTL_SECONDS", "1")
    assert provider_service.get_global_system_prompt() == "first"
    assert provider_service.get_global_system_prompt() == "first"
    assert provider_service.get_global_system_prompt() == "second"


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
