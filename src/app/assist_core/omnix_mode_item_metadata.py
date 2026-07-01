from __future__ import annotations

from typing import Any

from .omnix_mode_metadata import omnix_mode_metadata_payload


def omnix_mode_item_metadata_payload(mode: str) -> dict[str, Any]:
    payload = omnix_mode_metadata_payload(mode)
    if payload.get("ok") is not True:
        return payload
    return {
        **payload,
        "single": True,
    }
