"""RPG-owned boundary to the process provider service.

Deterministic RPG packages may depend on this adapter, but not on live provider
implementations directly. Tests can replace these functions without importing
provider packages inside deterministic modules.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def rpg_llm_route() -> tuple[str, str] | None:
    """RPG's provider and model from the settings' model roles (``effective_llm_route``).

    The model is the provider's own name for it (``llm:claude_cli:haiku`` is
    ``haiku``); a model of another provider is not used. None when the
    settings name no provider.
    """
    try:
        from app.settings.access import load_settings
        from app.settings.effective_defaults import effective_llm_route
        from app.settings.profile_repository import load_settings_profile

        from app.providers.model_route import ModelRoute

        route = ModelRoute.parse(*effective_llm_route(load_settings_profile(load_settings()), "rpg", "turn"))
    except Exception:
        # Unreadable settings leave RPG on the provider's own default route.
        logger.debug("rpg_llm_route_unavailable", exc_info=True)
        return None
    return (route.provider, route.own_model) if route.provider else None


def routed_provider(*, counted: bool = True) -> Any:
    """The provider RPG's model calls use: its settings route, or the app default.

    Its calls are counted for the turn making them (``model_calls``); the narrative writer counts its own.
    """
    from app.apps.rpg.foundation.model_calls import CountedProvider
    from app.providers import service

    route = rpg_llm_route()
    provider = service.get_provider() if route is None else service.get_routed_provider(*route)
    return CountedProvider(provider) if counted and provider is not None else provider


def get_provider() -> Any:
    from app.apps.rpg.foundation.llm_gateway_adapter import adapt_base_provider

    return adapt_base_provider(routed_provider())
