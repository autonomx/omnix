"""Small shared helpers for RPG ability modules."""
from __future__ import annotations


from typing import Any


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_")


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _non_empty_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
