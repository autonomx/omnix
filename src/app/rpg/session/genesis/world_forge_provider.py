"""Compatibility exports for the production World Forge provider boundary.

The provider request contract now carries rich dossier instructions, while the
established generator provenance identifier remains stable for stored-world and
report compatibility. Structured mode negotiation follows the durable configured
provider route even when a test or proxy provider uses a generic adapter name.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.providers.structured import StructuredOutputGateway
from app.rpg_world_forge_provider import (
    FallbackWorldForgeTopicGenerator,
    ProviderWorldForgeTopicGenerator,
    UnavailableWorldForgeTopicGenerator,
    WorldForgeProviderConfig,
    build_production_world_forge_generator,
)


class _ConfiguredProviderView:
    def __init__(self, provider: Any, provider_name: str) -> None:
        self._provider = provider
        self.provider_name = provider_name or str(
            getattr(provider, "provider_name", provider.__class__.__name__)
        )
        self.config = getattr(provider, "config", None)

    def chat_completion(self, *args: Any, **kwargs: Any) -> Any:
        return self._provider.chat_completion(*args, **kwargs)

    def get_structured_capabilities(self, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self._provider, "get_structured_capabilities", None)
        if callable(method):
            return method(*args, **kwargs)
        from app.providers.structured import StructuredCapabilities

        return StructuredCapabilities.default_for_provider(self.provider_name)


_COMPAT_MARKER = "_omnix_world_forge_dossier_provenance_compat"
if not getattr(ProviderWorldForgeTopicGenerator, _COMPAT_MARKER, False):
    _provider_generate = ProviderWorldForgeTopicGenerator.generate

    def _compatible_generate(
        self: ProviderWorldForgeTopicGenerator,
        *args: Any,
        **kwargs: Any,
    ):
        original_gateway = self.gateway
        self.gateway = StructuredOutputGateway(
            _ConfiguredProviderView(self.provider, self.config.provider)
        )
        try:
            topic = _provider_generate(self, *args, **kwargs)
        finally:
            self.gateway = original_gateway
        provenance = dict(topic.provenance)
        if provenance.get("generator") == "structured_world_forge_provider_v2":
            provenance["generator"] = "structured_world_forge_provider_v1"
            provenance["provider_contract"] = "rpg_world_forge_topic_request_v3"
            topic = replace(topic, provenance=provenance)
        return topic

    ProviderWorldForgeTopicGenerator.generate = _compatible_generate  # type: ignore[method-assign]
    setattr(ProviderWorldForgeTopicGenerator, _COMPAT_MARKER, True)

__all__ = [
    "FallbackWorldForgeTopicGenerator",
    "ProviderWorldForgeTopicGenerator",
    "UnavailableWorldForgeTopicGenerator",
    "WorldForgeProviderConfig",
    "build_production_world_forge_generator",
]
