"""Compatibility exports for the production World Forge provider boundary.

The provider request contract now carries rich dossier instructions, but the
established generator provenance identifier remains stable for stored-world and
report compatibility. The dossier schema is recorded separately.
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

    def _compatible_generate(self: ProviderWorldForgeTopicGenerator, *args: Any, **kwargs: Any):
        topic = _provider_generate(self, *args, **kwargs)
        provenance = dict(topic.provenance)
        if provenance.get("generator") == "structured_world_forge_provider_v2":
            provenance["generator"] = "structured_world_forge_provider_v1"
            provenance["provider_contract"] = "rpg_world_forge_topic_request_v2"
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
