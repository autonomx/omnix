"""Deterministic values for late-roadmap profile extensions."""
from __future__ import annotations

from typing import Any

from .world_forge_information_locality import deterministic_information_locality_signature


def extension_structured_value(
    field_id: str,
    *,
    index: int,
    entity_kind: str,
) -> dict[str, Any] | None:
    del entity_kind
    if field_id == "information_locality_signature":
        return deterministic_information_locality_signature(index)
    return None


def same_domain_reference_fields() -> frozenset[str]:
    return frozenset()


__all__ = ["extension_structured_value", "same_domain_reference_fields"]
