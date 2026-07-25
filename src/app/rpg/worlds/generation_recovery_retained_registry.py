"""Build a reviewable registry from a malformed but information-bearing response."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.rpg_world_forge_provider import (
    WorldForgeEntityRegistryItem,
    WorldForgeEntityRegistryResponse,
)

_MAX_RETAINED_TEXT = 65_536


def _candidate_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("entities", "items", "records", "results"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return [dict(value)]
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            rows = [dict(item) for item in value if isinstance(item, Mapping)]
            if rows:
                return rows
    return []


def retained_registry_response(
    *,
    expected_topic_id: str,
    allocated_entity_ids: tuple[str, ...],
    decoded_payload: Mapping[str, Any] | None,
    raw_text: str,
    error: Exception,
) -> WorldForgeEntityRegistryResponse:
    """Preserve known registry identity and use visible review placeholders as needed."""

    payload = dict(decoded_payload or {})
    rows = _candidate_rows(payload)
    by_id = {
        str(row.get("id") or row.get("entity_id") or ""): row
        for row in rows
        if str(row.get("id") or row.get("entity_id") or "")
    }
    entities: list[WorldForgeEntityRegistryItem] = []
    for index, entity_id in enumerate(allocated_entity_ids):
        row = by_id.get(entity_id) or (rows[index] if index < len(rows) else {})
        name = str(row.get("name") or row.get("title") or "").strip()
        role = str(row.get("role") or row.get("type") or row.get("category") or "").strip()
        distinction = str(
            row.get("distinction")
            or row.get("description")
            or row.get("summary")
            or ""
        ).strip()
        entities.append(
            WorldForgeEntityRegistryItem(
                id=entity_id,
                name=name or f"Review required {index + 1}",
                role=role or "review required",
                distinction=distinction or "Retained from malformed registry output.",
            )
        )
    provenance = dict(payload.get("provenance") or {}) if isinstance(
        payload.get("provenance"), Mapping
    ) else {}
    provenance["structured_recovery_retained_registry"] = {
        "error_type": type(error).__name__,
        "error": str(error),
        "decoded_candidate": payload if decoded_payload is not None else None,
        "raw_text": raw_text[:_MAX_RETAINED_TEXT] if decoded_payload is None else "",
        "truncated": decoded_payload is None and len(raw_text) > _MAX_RETAINED_TEXT,
    }
    return WorldForgeEntityRegistryResponse(
        topic_id=expected_topic_id,
        entities=entities,
        provenance=provenance,
    )


__all__ = ["retained_registry_response"]
