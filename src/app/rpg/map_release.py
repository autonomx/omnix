"""Final save/load, replay, and release validation for interactive RPG maps."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from app.rpg.map_overlay_projection import project_dynamic_map_overlay
from app.rpg.map_projection import MAP_STATE_SCHEMA_VERSION, project_session_map_overlay
from app.rpg.map_repository import MapDefinitionNotFound, MapDefinitionRepository, default_map_repository
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


def map_state_digest(session: Mapping[str, object]) -> str:
    return _digest(persisted_map_state(session))


def replay_map_projection(
    session: Mapping[str, object],
    map_id: str | None = None,
    repository: MapDefinitionRepository | None = None,
) -> MapReplayProjection:
    repository = repository or default_map_repository()
    map_state = persisted_map_state(session)
    active_map_id = str(map_id or map_state.get("current_map_id") or "")
    if not active_map_id:
        raise ValueError("current_map_id_unavailable")
    definition = repository.get(active_map_id)
    overlay = project_session_map_overlay(session, active_map_id, repository)
    dynamic = project_dynamic_map_overlay(session, definition)
    projection_payload = {
        "definition_revision": definition.definition_revision,
        "overlay": overlay,
        "dynamic": dynamic,
    }
    return MapReplayProjection(
        map_id=active_map_id,
        definition_revision=definition.definition_revision,
        overlay_revision=overlay.overlay_revision,
        session_turn_index=overlay.session_turn_index,
        persisted_state_digest=map_state_digest(session),
        projection_digest=_digest(projection_payload),
    )


def validate_map_release_session(
    session: Mapping[str, object],
    repository: MapDefinitionRepository | None = None,
) -> MapReleaseReport:
    repository = repository or default_map_repository()
    state = _mapping(session.get("state"))
    map_state = persisted_map_state(session)
    current_map_id = str(map_state.get("current_map_id") or "")
    current_location_id = str(map_state.get("current_location_id") or "")
    issues: list[str] = []
    if not map_state:
        issues.append("map_state_unavailable")
    if int(map_state.get("schema_version") or 0) != MAP_STATE_SCHEMA_VERSION:
        issues.append("map_state_schema_unsupported")
    if not current_map_id:
        issues.append("current_map_id_unavailable")
    if not current_location_id:
        issues.append("current_location_id_unavailable")
    player = _mapping(state.get("player"))
    player_location_id = str(player.get("location_id") or "")
    if player_location_id and current_location_id and player_location_id != current_location_id:
        issues.append("player_map_location_mismatch")
    projection = None
    if current_map_id:
        try:
            projection = replay_map_projection(session, current_map_id, repository)
            definition = repository.get(current_map_id)
            if not any(item.location_id == current_location_id for item in definition.objects):
                issues.append("current_location_not_in_definition")
        except MapDefinitionNotFound:
            issues.append("map_definition_not_found")
        except ValueError as exc:
            issues.append(str(exc))
    return MapReleaseReport(
        ready=not issues,
        issues=tuple(dict.fromkeys(issues)),
        current_map_id=current_map_id,
        current_location_id=current_location_id,
        persisted_state_digest=map_state_digest(session),
        projection=projection,
    )


def json_round_trip_session(session: Mapping[str, object]) -> dict[str, object]:
    """Model the durable JSON save/load boundary used by session persistence."""

    return json.loads(json.dumps(deepcopy(dict(session)), ensure_ascii=False, sort_keys=True))


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
