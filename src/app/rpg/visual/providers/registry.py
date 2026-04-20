from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Tuple, Type

from .base import BaseImageProvider
from .disabled_provider import DisabledImageProvider
from .flux_klein_provider import FluxKleinImageProvider


ProviderFactory = Callable[[Dict[str, Any]], BaseImageProvider]


def _provider_ctor(provider_cls: Type[BaseImageProvider]) -> ProviderFactory:
    def _factory(config: Dict[str, Any]) -> BaseImageProvider:
        return provider_cls(config or {})
    return _factory


_REGISTRY: Dict[str, Dict[str, Any]] = {
    "disabled": {
        "factory": _provider_ctor(DisabledImageProvider),
        "label": "Disabled",
        "runtime_validator": None,
    },
    "flux_klein": {
        "factory": _provider_ctor(FluxKleinImageProvider),
        "label": "FLUX.2 [klein] 4B",
        "runtime_validator": "flux_klein",
    },
}


def list_visual_provider_keys() -> List[str]:
    return sorted(_REGISTRY.keys())


def list_visual_provider_options() -> List[Dict[str, str]]:
    return [
        {
            "key": key,
            "label": entry["label"],
        }
        for key, entry in sorted(_REGISTRY.items())
    ]


def has_visual_provider(provider_key: str) -> bool:
    return provider_key in _REGISTRY


def _normalize_provider_key(provider_key: str | None) -> str:
    key = (provider_key or "").strip().lower()
    if not key:
        return "flux_klein"
    if key in {"none", "off", "disabled"}:
        return "disabled"
    return key


def resolve_visual_provider_key(config: Dict[str, Any] | None = None) -> str:
    cfg = dict(config or {})

    env_key = os.environ.get("OMNIX_VISUAL_PROVIDER", "").strip()
    if env_key:
        key = _normalize_provider_key(env_key)
        if has_visual_provider(key):
            return key

    enabled = cfg.get("enabled")
    if enabled is False:
        return "disabled"

    key = _normalize_provider_key(
        cfg.get("visual_provider")
        or cfg.get("provider")
        or cfg.get("image_provider")
    )
    if has_visual_provider(key):
        return key

    return "flux_klein"


def build_visual_provider(config: Dict[str, Any] | None = None) -> Tuple[str, BaseImageProvider]:
    cfg = dict(config or {})
    key = resolve_visual_provider_key(cfg)
    entry = _REGISTRY.get(key)
    if not entry:
        key = "disabled"
        entry = _REGISTRY[key]
    provider = entry["factory"](cfg)
    return key, provider


def get_visual_provider_runtime_validator(provider_key: str) -> str | None:
    entry = _REGISTRY.get(_normalize_provider_key(provider_key))
    if not entry:
        return None
    return entry.get("runtime_validator")