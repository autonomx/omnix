"""Global image provider registry (IMG-7)."""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def list_image_providers() -> List[Dict[str, Any]]:
    return [
        {
            "key": "flux_klein",
            "label": "FLUX.2 [klein] 4B",
            "status": "available",
            "supports_local_model": True,
            "supports_download": True,
        },
        {
            "key": "mock",
            "label": "Mock Image Provider",
            "status": "available",
            "supports_local_model": False,
            "supports_download": False,
        },
    ]


def get_image_provider_keys() -> List[str]:
    return [item["key"] for item in list_image_providers()]


def is_supported_image_provider(provider_name: str) -> bool:
    provider_name = _safe_str(provider_name).strip().lower()
    return provider_name in set(get_image_provider_keys())
