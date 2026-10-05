"""Shared helpers for runtime narration contract modules."""
from __future__ import annotations

from typing import Any, Dict, List

NARRATION_FORMAT_VERSION = "rpg_narration_v2"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().strip().split())
