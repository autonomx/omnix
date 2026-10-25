"""Public entry points for the World Forge provider."""

from typing import Any, Callable, Mapping

from app.apps.rpg.genesis.forge.world_forge_contract import CampaignTopicNode
from app.apps.rpg.genesis.forge.world_forge_generation import GeneratedTopic
from app.apps.rpg.genesis.worlds.providers.world_forge_foundation import (
    WorldForgeDossier,
    WorldForgeEntityRegistryItem,
    WorldForgeEntityRegistryResponse,
    WorldForgeProviderConfig,
    WorldForgeTopicResponse,
    _entity_registry_contract,
    _entity_registry_payload,
    _entity_registry_system_prompt,
    _model_rows,
    _payload,
    _system_prompt,
    _token_estimate,
    _topic_contract,
)
from app.apps.rpg.genesis.worlds.providers.world_forge_generator import (
    ProviderWorldForgeTopicGenerator,
)


__all__ = [
    "ProviderWorldForgeTopicGenerator",
    "UnavailableWorldForgeTopicGenerator",
    "WorldForgeDossier",
    "WorldForgeEntityRegistryItem",
    "WorldForgeEntityRegistryResponse",
    "WorldForgeProviderConfig",
    "WorldForgeTopicResponse",
    "_entity_registry_contract",
    "_entity_registry_payload",
    "_entity_registry_system_prompt",
    "_model_rows",
    "_payload",
    "_system_prompt",
    "_token_estimate",
    "_topic_contract",
    "attach_world_forge_progress_callback",
]


def attach_world_forge_progress_callback(
    generator: Any,
    callback: Callable[[Mapping[str, Any]], None],
) -> Callable[[], None]:
    """Attach a checkpoint callback through production generator wrappers.

    The production route can wrap a provider generator in validation, reference-safe,
    and fallback adapters.  This keeps batch checkpoints independent of that wiring.
    """

    configured: list[
        tuple[ProviderWorldForgeTopicGenerator, Callable[[Mapping[str, Any]], None] | None]
    ] = []
    visited: set[int] = set()

    def visit(value: Any) -> None:
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if isinstance(value, ProviderWorldForgeTopicGenerator):
            configured.append((value, value.set_progress_callback(callback)))
            return
        nested = getattr(value, "generator", None)
        if nested is not None:
            visit(nested)
        for nested_generator in getattr(value, "generators", ()):
            visit(nested_generator)

    visit(generator)

    def detach() -> None:
        for provider, previous in configured:
            provider.set_progress_callback(previous)

    return detach


class UnavailableWorldForgeTopicGenerator:
    """Fail launch-required generation instead of publishing placeholder canon."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, node: CampaignTopicNode, **kwargs: Any) -> GeneratedTopic:
        raise RuntimeError(f"{self.reason}: {node.topic_id}")
