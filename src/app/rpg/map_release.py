"""Final save/load, replay, and release validation for interactive RPG maps."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
from typing import Any

from app.rpg.map_serialization import canonical_map_bytes

_TRANSIENT_MAP_KEYS = {
    "active_object_id",
    "hover_object_id",
    "selected_object_id",
    "ui_state",
    "viewport",
    "viewport_by_map",
}


@dataclass(frozen=True)
class MapReplayProjection:
    map_id: str
    definition_revision: str
    overlay_revision: int
    session_turn_index: int
    persisted_state_digest: str
    projection_digest: str


@dataclass(frozen=True)
class MapReleaseReport:
    ready: bool
    issues: tuple[str, ...]
    current_map_id: str
    current_location_id: str
    persisted_state_digest: str
    projection: MapReplayProjection | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def persisted_map_state(session: Mapping[str, object]) -> dict[str, object]:
    """Return deterministic save state with browser-only fields removed."""

    state = _mapping(session.get("state"))
    map_state = _mapping(state.get("map_state"))
    return _clean_mapping(map_state)


def _clean_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in sorted(value):
        if key in _TRANSIENT_MAP_KEYS:
            continue
        result[str(key)] = _clean_value(value[key])
    return result


def _clean_value(value: object) -> Any:
    if isinstance(value, Mapping):
        return _clean_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_clean_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _digest(value: object) -> str:
    return f"sha256:{hashlib.sha256(canonical_map_bytes(value)).hexdigest()}"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}
