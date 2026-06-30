from __future__ import annotations

from typing import Any

from .omnix_mode_router import omnix_mode_router_payload


def omnix_mode_metadata_payload(mode: str | None = None) -> dict[str, Any]:
    payload = omnix_mode_router_payload(mode)
    return {
        **payload,
        "source": "omnix_mode_metadata",
        "read_only": True,
        "executes": False,
    }
