"""RPG's model calls, the narrative writer included, follow the settings' model route (WP-8.6)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.apps.rpg.foundation import provider_access
from app.apps.rpg.narration import narrative_provider
from app.providers import service
from app.providers.base import ProviderConfig


def _route(monkeypatch, provider_id: str, model_id: str) -> None:
    import app.settings.access as access
    import app.settings.effective_defaults as defaults
    import app.settings.profile_repository as profiles

    monkeypatch.setattr(access, "load_settings", lambda: {})
    monkeypatch.setattr(profiles, "load_settings_profile", lambda _settings: object())
    monkeypatch.setattr(defaults, "effective_llm_route", lambda _profile, _module, _task: (provider_id, model_id))


@pytest.mark.parametrize(
    ("provider_id", "model_id", "expected"),
    [
        ("llm:claude_cli", "llm:claude_cli:haiku", ("claude_cli", "haiku")),
        ("llm:claude_cli", "llm:lmstudio:gemma", ("claude_cli", "")),
        ("llm:lmstudio", "gemma-4", ("lmstudio", "gemma-4")),
        ("", "llm:claude_cli:haiku", None),
    ],
)
def test_the_route_names_the_providers_own_model(monkeypatch, provider_id, model_id, expected) -> None:
    _route(monkeypatch, provider_id, model_id)
    assert provider_access.rpg_llm_route() == expected


def test_without_an_override_the_writer_uses_the_route(monkeypatch) -> None:
    for name in ("OMNIX_RPG_NARRATIVE_PROVIDER", "OMNIX_LLM_PROVIDER", "OMNIX_RPG_NARRATIVE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OMNIX_RPG_NARRATIVE_WRITER_MODE", "auto")
    provider = SimpleNamespace(provider_name="claude_cli")
    monkeypatch.setattr(provider_access, "rpg_llm_route", lambda: ("claude_cli", "haiku"))
    monkeypatch.setattr(provider_access, "routed_provider", lambda: provider)

    writer = narrative_provider.build_production_narrative_writer()

    assert isinstance(writer, narrative_provider.ProductionStructuredNarrativeWriter)
    generator = writer.generator
    assert generator.transport_provider is provider
    assert (generator.config.provider, generator.config.model) == ("claude_cli", "haiku")


def test_an_offline_mode_still_writes_deterministically(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_RPG_NARRATIVE_WRITER_MODE", "deterministic")
    monkeypatch.setattr(provider_access, "rpg_llm_route", lambda: pytest.fail("offline mode reads no route"))
    writer = narrative_provider.build_production_narrative_writer()
    assert type(writer).__name__ == "DeterministicNarrativeWriter"


def test_a_routed_model_gets_its_own_cached_provider(monkeypatch) -> None:
    built: list[ProviderConfig] = []

    class _Registry:
        def create_provider(self, name, provider_config):
            built.append(provider_config)
            return SimpleNamespace(name=name, model=provider_config.model, close=lambda: None)

    monkeypatch.setattr(service, "_PROVIDERS", type(service._PROVIDERS)())
    monkeypatch.setattr(service, "get_registry", lambda: _Registry())
    monkeypatch.setattr(service, "load_settings", lambda: {})
    monkeypatch.setattr(service, "load_secrets", lambda: {})
    monkeypatch.setattr(
        service, "_provider_config",
        lambda name, _settings, _secrets: ("claude_cli", ProviderConfig(provider_type="claude_cli", model="sonnet")),
    )

    default = service.get_provider()
    routed = service.get_routed_provider("claude_cli", "haiku")

    assert (default.model, routed.model) == ("sonnet", "haiku")
    assert service.get_routed_provider("claude_cli", "haiku") is routed
    assert [config.model for config in built] == ["sonnet", "haiku"]


def test_a_replaced_get_provider_serves_routed_requests(monkeypatch) -> None:
    double = object()
    monkeypatch.setattr(service, "get_provider", lambda *args, **kwargs: double)
    assert service.get_routed_provider("claude_cli", "haiku") is double
