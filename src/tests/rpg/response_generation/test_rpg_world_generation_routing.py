from __future__ import annotations

from app.providers.base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg_world_forge_provider import ProviderWorldForgeTopicGenerator
from app.rpg.worlds import generation_routing


class _Provider(BaseProvider):
    provider_name = "lmstudio"

    def __init__(self) -> None:
        self.config = ProviderConfig(provider_type="lmstudio", model="cached-model")

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool = False,
        **kwargs,
    ) -> ChatResponse:
        return ChatResponse(content="{}", model=model or "cached-model")

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def test_configured_route_resolves_once_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        generation_routing,
        "_settings_route",
        lambda: ("lmstudio", "qwen-world-forge"),
    )

    route = generation_routing.resolve_world_forge_route(
        "configured",
        "configured",
        environ={},
    )

    assert route.provider == "lmstudio"
    assert route.model == "qwen-world-forge"
    assert route.source == "settings_control_center"


def test_explicit_route_is_not_replaced_by_current_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        generation_routing,
        "_settings_route",
        lambda: ("cerebras", "different-model"),
    )

    route = generation_routing.resolve_world_forge_route(
        "lmstudio",
        "qwen-durable",
        environ={},
    )

    assert route.provider == "lmstudio"
    assert route.model == "qwen-durable"
    assert route.source == "explicit"


def test_job_generator_uses_stored_provider_and_model(monkeypatch) -> None:
    from app import shared

    provider = _Provider()
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: provider if provider_name == "lmstudio" else None,
    )

    generator = generation_routing.build_world_forge_generator_from_settings(
        {
            "provider_route": "lmstudio",
            "model": "qwen-durable",
        }
    )

    assert isinstance(generator, ReferenceSafeWorldForgeGenerator)
    assert isinstance(generator.generator, ProviderWorldForgeTopicGenerator)
    assert generator.generator.provider is provider
    assert generator.generator.config.provider == "lmstudio"
    assert generator.generator.config.model == "qwen-durable"


def test_unresolved_job_route_fails_closed() -> None:
    generator = generation_routing.build_world_forge_generator_from_settings(
        {"provider_route": "configured", "model": "configured"}
    )

    try:
        generator.generate(None)  # type: ignore[arg-type]
    except RuntimeError as exc:
        assert "unresolved provider route" in str(exc)
    else:
        raise AssertionError("unresolved durable routes must fail closed")
