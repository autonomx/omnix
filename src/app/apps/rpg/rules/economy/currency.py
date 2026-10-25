from __future__ import annotations

from typing import Any, Dict
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict

Currency = Dict[str, int]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_currency(value: Any) -> Currency:
    value = _safe_dict(value)
    return {
        "gold": max(0, _safe_int(value.get("gold"), 0)),
        "silver": max(0, _safe_int(value.get("silver"), 0)),
        "copper": max(0, _safe_int(value.get("copper"), 0)),
    }
