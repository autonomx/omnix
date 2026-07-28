from __future__ import annotations

import pytest

from app.providers.base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
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


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="realm",
        title="Realm",
        category="lore",
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="public",
        target_count=1,
    )


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
        {"provider_route": "lmstudio", "model": "qwen-durable"}
    )

    assert isinstance(generator, ReferenceSafeWorldForgeGenerator)
    assert isinstance(generator.generator, ProviderWorldForgeTopicGenerator)
    assert generator.generator.transport_provider is provider
    assert generator.generator.config.provider == "lmstudio"
    assert generator.generator.config.model == "qwen-durable"


def test_unresolved_job_route_fails_closed() -> None:
    generator = generation_routing.build_world_forge_generator_from_settings(
        {"provider_route": "configured", "model": "configured"}
    )
    with pytest.raises(RuntimeError, match="no concrete provider and model"):
        generator.generate(
            _node(),
            seed=1,
            campaign_context={},
            dependency_topics={},
        )


def test_configured_route_without_provider_and_model_fails_when_lmstudio_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(generation_routing, "_settings_route", lambda: ("", ""))
    monkeypatch.setattr(generation_routing, "_auto_detect_lmstudio_route", lambda: ("", ""))

    with pytest.raises(
        generation_routing.WorldForgeRouteUnavailableError,
        match="world_forge_provider_and_model_required",
    ):
        generation_routing.resolve_world_forge_route(
            "configured",
            "configured",
            environ={},
        )


def test_configured_route_auto_detects_loaded_lmstudio_model(monkeypatch) -> None:
    monkeypatch.setattr(generation_routing, "_settings_route", lambda: ("", ""))
    monkeypatch.setattr(
        generation_routing,
        "_auto_detect_lmstudio_route",
        lambda: ("lmstudio", "loaded-local-model"),
    )

    route = generation_routing.resolve_world_forge_route(
        "configured",
        "configured",
        environ={},
    )

    assert route.provider == "lmstudio"
    assert route.model == "loaded-local-model"
    assert route.source == "lmstudio_auto_detected"


def test_deterministic_route_is_explicit_test_only() -> None:
    with pytest.raises(
        generation_routing.WorldForgeRouteUnavailableError,
        match="deterministic_world_forge_route_is_test_only",
    ):
        generation_routing.resolve_world_forge_route(
            "deterministic",
            "reference-safe",
            environ={},
        )

    route = generation_routing.resolve_world_forge_route(
        "deterministic",
        "reference-safe",
        environ={},
        allow_deterministic=True,
    )
    assert route.provider == "deterministic"
    assert route.source == "explicit_test"
