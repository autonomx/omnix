"""Compatibility exports for the production World Forge provider boundary.

The provider request contract now carries rich dossier instructions, while the
established generator provenance identifier remains stable for stored-world and
report compatibility. The compatibility wrapper does not import provider-layer
infrastructure so deterministic genesis modules remain provider-free.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rpg_world_forge_provider import (
    FallbackWorldForgeTopicGenerator,
    ProviderWorldForgeTopicGenerator,
    UnavailableWorldForgeTopicGenerator,
    WorldForgeProviderConfig,
    build_production_world_forge_generator,
)

_COMPAT_MARKER = "_omnix_world_forge_dossier_provenance_compat"
if not getattr(ProviderWorldForgeTopicGenerator, _COMPAT_MARKER, False):
    _provider_generate = ProviderWorldForgeTopicGenerator.generate

    def _compatible_generate(
        self: ProviderWorldForgeTopicGenerator,
        *args: Any,
        **kwargs: Any,
    ):
        configured_provider = str(self.config.provider or "").strip()
        original_provider_name = getattr(self.provider, "provider_name", None)
        if configured_provider:
            self.provider.provider_name = configured_provider
        try:
            topic = _provider_generate(self, *args, **kwargs)
        finally:
            if original_provider_name is None:
                try:
                    delattr(self.provider, "provider_name")
                except AttributeError:
                    pass
            else:
                self.provider.provider_name = original_provider_name
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
