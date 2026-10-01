from __future__ import annotations

from copy import deepcopy

from app.config.defaults import DEFAULT_SETTINGS
from app.platform import settings_control
from app.platform.settings import apply_settings_payload
from app.providers import service as provider_service
from tests.support.settings_runtime import install_settings_test_runtime


def test_nested_setting_patches_preserve_unmentioned_configuration() -> None:
    settings = deepcopy(DEFAULT_SETTINGS)
    secrets = {"api_keys": {"openrouter": "or-secret-1234"}}

    changed = apply_settings_payload(
        settings,
        secrets,
        {
            "llamacpp": {"download_location": "custom-llm", "auto_start": True},
            "image": {"flux_klein": {"local_dir": "D:/models/flux-klein", "width": 1024}},
            "rpg_visual": {"enabled": True, "flux_klein": {"local_dir": "D:/models/rpg-flux"}},
        },
    )

    assert changed is False
    assert settings["llamacpp"]["download_location"] == "custom-llm"
    assert settings["llamacpp"]["auto_start"] is True
    assert settings["llamacpp"]["model"] == DEFAULT_SETTINGS["llamacpp"]["model"]
    assert settings["image"]["flux_klein"]["local_dir"] == "D:/models/flux-klein"
    assert settings["image"]["flux_klein"]["width"] == 1024
    assert settings["image"]["flux_klein"]["download_dir"] == DEFAULT_SETTINGS["image"]["flux_klein"]["download_dir"]
    assert settings["rpg_visual"]["enabled"] is True
    assert settings["rpg_visual"]["provider"] == DEFAULT_SETTINGS["rpg_visual"]["provider"]
    assert settings["rpg_visual"]["flux_klein"]["portrait_width"] == DEFAULT_SETTINGS["rpg_visual"]["flux_klein"]["portrait_width"]
    assert secrets["api_keys"]["openrouter"] == "or-secret-1234"


def test_provider_secret_update_uses_secret_store_and_invalidates_cache(monkeypatch) -> None:
    service, secret_store = install_settings_test_runtime(
        monkeypatch,
        secrets={"api_keys": {"openrouter": "or-secret-1234"}},
    )
    provider_service._PROVIDERS["cached-provider"] = provider_service._CachedProvider(
        object(), provider_service.time.monotonic() + 60.0
    )

    result = settings_control.save_settings_payload(
        {
            "openrouter": {
                "api_key": "or-secret-5678",
                "model": "anthropic/claude-sonnet",
            }
        }
    )

    assert result.success is True
    assert secret_store["api_keys"]["openrouter"] == "or-secret-5678"
    assert service.values["openrouter"]["model"] == "anthropic/claude-sonnet"
    assert "api_key" not in service.values["openrouter"]
    assert not provider_service._PROVIDERS
    assert settings_control.get_settings_payload().settings["openrouter"]["api_key"] == "***5678"


def test_provider_cache_subscribes_to_provider_settings(monkeypatch) -> None:
    service, _secrets = install_settings_test_runtime(monkeypatch)
    closed: list[bool] = []

    class CachedProvider:
        provider_name = "lmstudio"

        def close(self) -> None:
            closed.append(True)

    provider = CachedProvider()

    class Registry:
        def create_provider(self, name, *, provider_config):
            del name, provider_config
            return provider

    monkeypatch.setattr(provider_service, "get_registry", lambda: Registry())
    monkeypatch.setattr(provider_service, "load_secrets", lambda: {"api_keys": {}})
    provider_service.invalidate_provider_cache()

    assert provider_service.get_provider() is provider
    service.set("provider", "cerebras", expected_revision=0)

    assert not provider_service._PROVIDERS
    assert closed == [True]


def test_global_prompt_change_does_not_invalidate_provider_cache(monkeypatch) -> None:
    service, secret_store = install_settings_test_runtime(
        monkeypatch,
        secrets={"api_keys": {"openrouter": "or-secret-1234"}},
    )
    profile = settings_control.get_settings_payload().settings["settings_control_center"]
    initialized = settings_control.save_settings_payload(
        {
            "base_revision": profile["revision"],
            "settings_profile_patch": {"appearance": {"mode": "dark"}},
        }
    )
    assert initialized.success is True
    cached_instance = object()
    provider_service._PROVIDERS["cached-provider"] = provider_service._CachedProvider(
        cached_instance, provider_service.time.monotonic() + 60.0
    )

    result = settings_control.save_settings_payload(
        {"global_system_prompt": "Updated system prompt"}
    )

    assert result.success is True
    assert service.values["global_system_prompt"] == "Updated system prompt"
    assert secret_store["api_keys"]["openrouter"] == "or-secret-1234"
    assert provider_service._PROVIDERS["cached-provider"].instance is cached_instance
    provider_service.invalidate_provider_cache()


def test_worker_and_audio_settings_use_typed_settings_entries(monkeypatch) -> None:
    service, secret_store = install_settings_test_runtime(
        monkeypatch,
        secrets={"api_keys": {"openrouter": "or-secret-1234"}},
    )

    result = settings_control.save_settings_payload(
        {
            "audio_provider_tts": "faster-qwen3-tts",
            "audio_provider_stt": "parakeet",
            "tts_worker_url": "http://127.0.0.1:9201",
            "stt_worker_url": "http://127.0.0.1:9202",
            "image_worker_url": "http://127.0.0.1:9203",
            "faster-qwen3-tts": {"model_dir": "D:/models/qwen-tts", "temperature": 0.7},
            "parakeet": {"base_url": "http://127.0.0.1:9204"},
        }
    )

    assert result.success is True
    assert service.values["tts_worker_url"] == "http://127.0.0.1:9201"
    assert service.values["stt_worker_url"] == "http://127.0.0.1:9202"
    assert service.values["image_worker_url"] == "http://127.0.0.1:9203"
    assert service.values["faster-qwen3-tts"]["model_dir"] == "D:/models/qwen-tts"
    assert service.values["parakeet"]["base_url"] == "http://127.0.0.1:9204"
    assert secret_store["api_keys"]["openrouter"] == "or-secret-1234"
