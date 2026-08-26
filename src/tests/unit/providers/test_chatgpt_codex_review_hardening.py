"""Review hardening coverage for the ChatGPT Codex integration."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.providers import ChatGPTCodexProvider, ProviderConfig, ProviderRegistry
from app.providers.facade import ProviderFacade


def test_relative_codex_path_resolves_before_subprocess_cwd_changes(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "tools" / "codex"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.chdir(tmp_path)

    resolved = ChatGPTCodexProvider._resolve_executable("./tools/codex")

    assert resolved == str(executable.resolve())
    assert Path(resolved).is_absolute()


def test_registry_preserves_explicit_codex_provider_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.shared.load_settings",
        lambda: {
            "settings_control_center": {
                "providerConfigs": {
                    "chatgptCodex": {
                        "model": "profile-model-that-must-not-win",
                        "reasoningEffort": "low",
                        "fastMode": False,
                        "codexPath": "profile-codex",
                        "transport": "app_server",
                    }
                }
            }
        },
    )
    explicit = ProviderConfig(
        provider_type="chatgpt_codex",
        model="gpt-explicit",
        timeout=17,
        max_retries=1,
        extra_params={
            "reasoning_effort": "high",
            "fast_mode": True,
            "codex_path": "explicit-codex",
            "transport": "app_server",
        },
    )
    registry = ProviderRegistry()
    registry.discover_providers()

    provider = registry.create_provider("chatgpt_codex", provider_config=explicit)

    assert isinstance(provider, ChatGPTCodexProvider)
    try:
        assert provider.config.model == "gpt-explicit"
        assert provider.config.timeout == 17
        assert provider.config.max_retries == 1
        assert provider.reasoning_effort == "high"
        assert provider.fast_mode is True
        assert provider.codex_path == "explicit-codex"
    finally:
        provider.close()


def test_provider_facade_surfaces_live_codex_catalog(monkeypatch) -> None:
    live_provider = SimpleNamespace(
        get_models=lambda: [
            SimpleNamespace(
                id="gpt-live-a",
                name="GPT Live A",
                metadata={
                    "source": "codex_app_server",
                    "supported_reasoning_efforts": ["none", "medium", "high"],
                },
            ),
            SimpleNamespace(
                id="gpt-live-b",
                name="GPT Live B",
                metadata={
                    "source": "codex_app_server",
                    "supported_reasoning_efforts": [{"effort": "low"}, {"effort": "high"}],
                },
            ),
        ]
    )
    monkeypatch.setattr("app.shared.get_provider", lambda name: live_provider if name == "chatgpt_codex" else None)
    facade = ProviderFacade(
        llm_lister=lambda: [
            {
                "name": "chatgpt_codex",
                "display_name": "ChatGPT Plus (Codex)",
                "capabilities": ["chat", "models"],
            }
        ],
        tts_lister=lambda: [],
        stt_lister=lambda: [],
        image_lister=lambda: [],
        visual_lister=lambda: [],
        settings_loader=lambda: {
            "settings_control_center": {
                "providerConfigs": {"chatgptCodex": {"model": "configured-fallback"}}
            }
        },
    )

    payload = facade.payload()
    codex_models = [model for model in payload.models if model.provider_id == "llm:chatgpt_codex"]

    assert [model.metadata["model_id"] for model in codex_models] == ["gpt-live-a", "gpt-live-b"]
    assert [model.label for model in codex_models] == ["GPT Live A", "GPT Live B"]
    assert codex_models[0].metadata["supported_reasoning_efforts"] == ["none", "medium", "high"]
    assert all("configured-fallback" not in model.id for model in codex_models)


def test_provider_facade_keeps_configured_codex_model_when_catalog_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.shared.get_provider", lambda _name: SimpleNamespace(get_models=lambda: []))
    facade = ProviderFacade(
        llm_lister=lambda: [{"name": "chatgpt_codex", "capabilities": ["chat", "models"]}],
        tts_lister=lambda: [],
        stt_lister=lambda: [],
        image_lister=lambda: [],
        visual_lister=lambda: [],
        settings_loader=lambda: {
            "settings_control_center": {
                "providerConfigs": {"chatgptCodex": {"model": "configured-fallback"}}
            }
        },
    )

    payload = facade.payload()
    codex_models = [model for model in payload.models if model.provider_id == "llm:chatgpt_codex"]

    assert len(codex_models) == 1
    assert codex_models[0].metadata["model_id"] == "configured-fallback"
    assert codex_models[0].metadata["source"] == "settings"
