"""Deterministic serialization and revision helpers for RPG map contracts."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping

from app.rpg.map_contracts import MapDefinition, MapOverlay


def canonical_map_json(value: object) -> str:
    """Serialize map data with stable ordering and compact separators."""

    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_map_bytes(value: object) -> bytes:
    return canonical_map_json(value).encode("utf-8")


def map_content_revision(value: object) -> str:
    digest = hashlib.sha256(canonical_map_bytes(value)).hexdigest()
    return f"sha256:{digest}"


def definition_revision(definition: MapDefinition) -> str:
    """Hash the definition while excluding its self-referential revision field."""

    return map_content_revision(replace(definition, definition_revision=""))


def with_definition_revision(definition: MapDefinition) -> MapDefinition:
    return replace(definition, definition_revision=definition_revision(definition))


def overlay_content_revision(overlay: MapOverlay) -> str:
    """Expose a content hash useful for replay assertions and cache diagnostics."""

    return map_content_revision(overlay)


def resource_envelope_payload(
    definition: MapDefinition,
    overlay: MapOverlay,
    *,
    known_definition_revision: str | None = None,
) -> dict[str, object]:
    revision = definition.definition_revision or definition_revision(definition)
    include_definition = known_definition_revision != revision
    return {
        "map_id": definition.map_id,
        "definition_revision": revision,
        "overlay_revision": overlay.overlay_revision,
        "session_turn_index": overlay.session_turn_index,
        "definition": _canonical_value(definition) if include_definition else None,
        "overlay": _canonical_value(overlay),
    }


def _canonical_value(value: object) -> Any:
    if is_dataclass(value):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical_value(item) for item in value), key=_stable_sort_key)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported_map_serialization_type:{type(value).__name__}")


def _stable_sort_key(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
