"""Single-entry authoritative mutation core for RPG map actions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, Mapping

from app.rpg.map_projection import increment_map_overlay_revision, project_session_map_overlay
from app.rpg.map_repository import MapDefinitionRepository, default_map_repository

MapActionType = Literal["travel", "inspect", "enter", "talk", "trade"]


@dataclass(frozen=True)
class MapActionRequest:
    action: MapActionType
    target_object_id: str
    definition_revision: str
    overlay_revision: int
    route_id: str | None = None
    client_action_id: str | None = None


class MapActionError(ValueError):
    def __init__(self, code: str, *, reason: str = "", status_code: int = 400) -> None:
        self.code = code
        self.reason = reason or code
        self.status_code = status_code
        super().__init__(self.reason)


def apply_map_action(
    session: Mapping[str, object],
    map_id: str,
    request: MapActionRequest,
    repository: MapDefinitionRepository | None = None,
) -> dict[str, object]:
    """Validate and apply one map action without bypassing session truth."""

    repository = repository or default_map_repository()
    definition = repository.get(map_id)
    overlay = project_session_map_overlay(session, map_id, repository)
    if overlay.availability != "ready":
        raise MapActionError("map_overlay_unavailable", reason=overlay.unavailable_reason, status_code=409)
    if request.definition_revision != definition.definition_revision:
        raise MapActionError("stale_definition_revision", status_code=409)
    if request.overlay_revision != overlay.overlay_revision:
        raise MapActionError("stale_overlay_revision", status_code=409)

    target = next((item for item in definition.objects if item.id == request.target_object_id), None)
    if target is None:
        raise MapActionError("map_object_not_found", status_code=404)
    if target.id not in overlay.discovered_object_ids:
        raise MapActionError("map_object_undiscovered", status_code=404)
    if target.id not in overlay.visible_object_ids:
        raise MapActionError("map_object_not_visible", status_code=409)

    existing = _existing_action(session, request.client_action_id)
    if existing is not None:
        return {
            "ok": True,
            "idempotent": True,
            "action_result": existing,
            "session": deepcopy(dict(session)),
            "overlay": overlay,
        }

    capability = next(
        (
            item
            for item in overlay.capabilities
            if item.type == request.action and item.target_object_id == target.id
        ),
        None,
    )
    if capability is None:
        raise MapActionError("map_action_not_available", status_code=409)
    if request.route_id and capability.route_id and request.route_id != capability.route_id:
        raise MapActionError("route_identity_mismatch", status_code=409)
    if not capability.enabled:
        reason = capability.disabled_reason or "map_action_disabled"
        raise MapActionError(reason, reason=reason, status_code=409)

    updated = deepcopy(dict(session))
    state = updated.get("state") if isinstance(updated.get("state"), dict) else {}
    map_state = state.get("map_state") if isinstance(state.get("map_state"), dict) else {}
    result: dict[str, object] = {
        "action": request.action,
        "target_object_id": target.id,
        "target_location_id": target.location_id,
        "route_id": capability.route_id,
        "changed": False,
    }

    if request.action == "travel":
        if not target.location_id:
            raise MapActionError("target_location_unavailable", status_code=409)
        previous_location_id = str(map_state.get("current_location_id") or "")
        map_state["current_location_id"] = target.location_id
        state["current_location_id"] = target.location_id
        state["current_location"] = target.label or target.location_id
        state["location"] = target.label or target.location_id
        player = state.get("player") if isinstance(state.get("player"), dict) else {}
        player["location_id"] = target.location_id
        state["player"] = player
        revision = increment_map_overlay_revision(state)
        result.update(
            {
                "changed": True,
                "previous_location_id": previous_location_id,
                "current_location_id": target.location_id,
                "overlay_revision": revision,
            }
        )
    elif request.action == "inspect":
        result.update(
            {
                "label": target.label,
                "description": target.description,
                "status": _object_status(map_state, target.id),
            }
        )
    else:
        result["requires_turn"] = True
        result["suggested_command"] = _suggested_command(request.action, target.label or target.id)

    _record_action(map_state, request, result)
    state["map_state"] = map_state
    updated["state"] = state
    projected = project_session_map_overlay(updated, map_id, repository)
    return {
        "ok": True,
        "idempotent": False,
        "action_result": result,
        "session": updated,
        "overlay": projected,
    }


def map_action_error_payload(error: MapActionError, map_id: str) -> dict[str, object]:
    return {
        "ok": False,
        "error": error.code,
        "reason": error.reason,
        "map_id": map_id,
        "requires_turn": error.reason in {
            "route_requires_encounter_check",
            "target_requires_expansion",
            "route_unknown",
        },
    }


def _existing_action(session: Mapping[str, object], client_action_id: str | None) -> Mapping[str, object] | None:
    if not client_action_id:
        return None
    state = session.get("state") if isinstance(session.get("state"), Mapping) else {}
    map_state = state.get("map_state") if isinstance(state.get("map_state"), Mapping) else {}
    for item in reversed(_sequence(map_state.get("action_history"))):
        if isinstance(item, Mapping) and item.get("client_action_id") == client_action_id:
            result = item.get("result")
            return result if isinstance(result, Mapping) else item
    return None


def _record_action(map_state: dict[str, object], request: MapActionRequest, result: Mapping[str, object]) -> None:
    history = [item for item in _sequence(map_state.get("action_history")) if isinstance(item, Mapping)]
    history.append(
        {
            "client_action_id": request.client_action_id,
            "action": request.action,
            "target_object_id": request.target_object_id,
            "result": dict(result),
        }
    )
    map_state["action_history"] = history[-32:]


def _object_status(map_state: Mapping[str, object], object_id: str) -> str:
    states = map_state.get("object_states") if isinstance(map_state.get("object_states"), Mapping) else {}
    state = states.get(object_id) if isinstance(states.get(object_id), Mapping) else {}
    return str(state.get("status") or "normal")


def _suggested_command(action: str, label: str) -> str:
    return {
        "enter": f"Enter {label}.",
        "talk": f"Talk to the people at {label}.",
        "trade": f"Trade at {label}.",
    }.get(action, f"Interact with {label}.")


def _sequence(value: object) -> tuple[object, ...]:
    return tuple(value) if isinstance(value, (list, tuple)) else ()
