from __future__ import annotations

from typing import Any

from .omnix_mode_metadata import omnix_mode_metadata_payload


def omnix_modes_metadata_payload() -> dict[str, Any]:
    payload = omnix_mode_metadata_payload()
    return {
        **payload,
        "mode_count": len(payload.get("routes", [])),
    }
