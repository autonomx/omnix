"""Resolve and execute the durable provider route stored with a World Forge run.

The browser may request the ``configured`` route, but a durable generation run must
record the concrete provider and model that will execute it. Workers then use those
stored values instead of re-resolving mutable global settings for every topic.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import os
from typing import Any, Mapping

from app.providers.registry import get_provider
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_generation import WorldForgeTopicGenerator
from app.rpg_world_forge_provider import (
    ProviderWorldForgeTopicGenerator,
    UnavailableWorldForgeTopicGenerator,
    WorldForgeProviderConfig,
)

_CONFIGURED_VALUES = {"", "auto", "configured", "settings"}
_DETERMINISTIC_VALUES = {"deterministic", "offline", "reference-safe", "test"}


@dataclass(frozen=True)
class ResolvedWorldForgeRoute:
    provider: str
    model: str
    source: str
    requested_provider: str
    requested_model: str

    @property
    def is_deterministic(self) -> bool:
        return self.provider == "deterministic"


def _provider_key(value: Any) -> str:
    provider = str(value or "").strip()
    if provider.startswith("llm:"):
        provider = provider.split(":", 1)[1]
    return provider.casefold()


def _model_key(value: Any) -> str:
    model = str(value or "").strip()
    parts = model.split(":", 2)
    if len(parts) == 3 and parts[0] == "llm":
        model = parts[2]
    return model


def _settings_route() -> tuple[str, str]:
    try:
        from app.platform.effective_defaults import effective_llm_route, load_effective_profile

        provider_id, model_id = effective_llm_route(
            load_effective_profile(),
            "rpg",
            "rpg.world_forge.generate",
        )
        return _provider_key(provider_id), _model_key(model_id)
    except Exception:
        return "", ""


def resolve_world_forge_route(
    provider_route: str = "configured",
    model: str = "configured",
    *,
    environ: Mapping[str, str] | None = None,
) -> ResolvedWorldForgeRoute:
    """Resolve a concrete route once, before a durable generation run is created."""

    env = environ if environ is not None else os.environ
    requested_provider = _provider_key(provider_route)
    requested_model = _model_key(model)
    explicit_provider = requested_provider not in _CONFIGURED_VALUES
    explicit_model = requested_model.casefold() not in _CONFIGURED_VALUES

    if requested_provider in _DETERMINISTIC_VALUES:
        return ResolvedWorldForgeRoute(
            "deterministic",
            "reference-safe",
            "explicit",
            requested_provider,
            requested_model,
        )

    env_provider = _provider_key(env.get("OMNIX_RPG_WORLD_FORGE_PROVIDER"))
    env_model = _model_key(env.get("OMNIX_RPG_WORLD_FORGE_MODEL"))
    settings_provider, settings_model = _settings_route()

    if explicit_provider:
        resolved_model = requested_model if explicit_model else ""
        if not resolved_model and env_provider == requested_provider:
            resolved_model = env_model
        if not resolved_model and settings_provider == requested_provider:
            resolved_model = settings_model
        return ResolvedWorldForgeRoute(
            requested_provider,
            resolved_model,
            "explicit",
            requested_provider,
            requested_model,
        )

    if env_provider:
        return ResolvedWorldForgeRoute(
            env_provider,
            requested_model if explicit_model else env_model,
            "world_forge_environment",
            requested_provider,
            requested_model,
        )

    if settings_provider:
        return ResolvedWorldForgeRoute(
            settings_provider,
            requested_model if explicit_model else settings_model,
            "settings_control_center",
            requested_provider,
            requested_model,
        )

    return ResolvedWorldForgeRoute(
        "deterministic",
        "reference-safe",
        "deterministic_fallback",
        requested_provider,
        requested_model,
    )


def build_world_forge_generator_from_settings(
    settings: Mapping[str, Any],
) -> WorldForgeTopicGenerator:
    """Build exactly the provider/model recorded in a claimed topic job."""

    provider_id = _provider_key(settings.get("provider_route"))
    model_id = _model_key(settings.get("model"))
    if provider_id in _CONFIGURED_VALUES:
        return UnavailableWorldForgeTopicGenerator(
            "durable World Forge job contains an unresolved provider route"
        )
    if provider_id in _DETERMINISTIC_VALUES or provider_id == "deterministic":
        return ReferenceSafeWorldForgeGenerator()

    config = replace(
        WorldForgeProviderConfig.from_environment(),
        mode="live",
        provider=provider_id,
        model=model_id,
    )
    provider = None
    try:
        from app import shared

        provider = shared.get_provider(provider_id)
    except Exception:
        provider = None
    if provider is None:
        try:
            provider = get_provider(
                provider_id,
                {
                    "api_key": config.api_key,
                    "base_url": config.base_url,
                    "model": config.model or None,
                    "timeout": config.timeout_seconds,
                    "max_retries": config.max_retries,
                },
            )
        except Exception as exc:
            return UnavailableWorldForgeTopicGenerator(
                f"durable World Forge provider {provider_id} could not initialize: {exc}"
            )
    if provider is None:
        return UnavailableWorldForgeTopicGenerator(
            f"durable World Forge provider {provider_id} is unavailable"
        )
    return ReferenceSafeWorldForgeGenerator(
        ProviderWorldForgeTopicGenerator(provider, config)
    )
