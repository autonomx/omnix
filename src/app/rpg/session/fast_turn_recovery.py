from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

FAST_TURN_RECOVERY_VERSION = "fast_turn_recovery_v1"


@dataclass(frozen=True)
class FastTurnRecoveryItem:
    task_type: str
    title: str
    priority: int
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format_version": FAST_TURN_RECOVERY_VERSION,
            "task_type": self.task_type,
            "title": self.title,
            "priority": self.priority,
            "background_only": True,
            "payload": dict(self.payload),
        }


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _short(value: Any, limit: int = 500) -> str:
    text = " ".join(_text(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _turn_id(result: Mapping[str, Any]) -> str:
    nested = _dict(result.get("result"))
    return _first_text(result.get("turn_id"), nested.get("turn_id"))


def _session_id(result: Mapping[str, Any], session: Mapping[str, Any] | None) -> str:
    manifest = _dict(_dict(session).get("manifest"))
    input_ref = _dict(result.get("input_ref"))
    return _first_text(manifest.get("session_id"), manifest.get("id"), input_ref.get("session_id"), result.get("session_id"))


def _player_input(result: Mapping[str, Any]) -> str:
    nested = _dict(result.get("result"))
    payload = _dict(result.get("input_payload"))
    return _first_text(result.get("player_input"), nested.get("player_input"), payload.get("player_input"), payload.get("command"))


def _visible_response(result: Mapping[str, Any]) -> str:
    nested = _dict(result.get("result"))
    visible = _dict(result.get("visible_response"))
    return _short(
        _first_text(
            result.get("final_narration"),
            result.get("narration"),
            result.get("summary"),
            visible.get("narration"),
            nested.get("final_narration"),
            nested.get("narration"),
            nested.get("summary"),
        ),
        900,
    )


def _has_world_signal(result: Mapping[str, Any]) -> bool:
    if _list(result.get("combat_event_cards")):
        return True
    for source in (result, _dict(result.get("result")), _dict(result.get("authoritative"))):
        if _dict(source.get("quest_update")) or _list(source.get("quest_updates")):
            return True
        if _dict(source.get("travel_result")):
            return True
        if _dict(source.get("combat_delta")) or _list(source.get("combat_events")):
            return True
    return False


def _base_payload(result: Mapping[str, Any], session: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "turn_id": _turn_id(result),
        "session_id": _session_id(result, session),
        "player_input": _short(_player_input(result), 500),
        "visible_response": _visible_response(result),
    }


def _enabled(task_type: str, enabled_tasks: Sequence[str] | None) -> bool:
    if enabled_tasks is None:
        return True
    normalized = {str(item).strip().casefold() for item in enabled_tasks if str(item).strip()}
    return task_type in normalized


def build_fast_turn_recovery_items(
    result: Mapping[str, Any],
    *,
    session: Mapping[str, Any] | None = None,
    enabled_tasks: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    result = _dict(result)
    payload = _base_payload(result, session)
    items: list[FastTurnRecoveryItem] = []
    if _enabled("memory", enabled_tasks) and (payload["player_input"] or payload["visible_response"]):
        items.append(FastTurnRecoveryItem("memory", "Extract turn memory", 20, {**payload, "scope": "memory"}))
    if _enabled("audit", enabled_tasks):
        items.append(FastTurnRecoveryItem("audit", "Review turn grounding", 30, {**payload, "scope": "audit"}))
    if _enabled("summary", enabled_tasks) and payload["visible_response"]:
        items.append(FastTurnRecoveryItem("summary", "Update rolling summary", 40, {**payload, "scope": "summary"}))
    if _enabled("world_update", enabled_tasks) and _has_world_signal(result):
        items.append(FastTurnRecoveryItem("world_update", "Process world follow-up", 50, {**payload, "scope": "world_update"}))
    return [item.as_dict() for item in sorted(items, key=lambda item: item.priority)]


def build_fast_turn_recovery_payload(
    result: Mapping[str, Any],
    *,
    session: Mapping[str, Any] | None = None,
    enabled_tasks: Sequence[str] | None = None,
) -> dict[str, Any]:
    items = build_fast_turn_recovery_items(result, session=session, enabled_tasks=enabled_tasks)
    return {
        "format_version": FAST_TURN_RECOVERY_VERSION,
        "background_only": True,
        "queued": len(items),
        "items": items,
    }


def attach_fast_turn_recovery(
    result: dict[str, Any],
    *,
    session: Mapping[str, Any] | None = None,
    enabled_tasks: Sequence[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    payload = build_fast_turn_recovery_payload(result, session=session, enabled_tasks=enabled_tasks)
    result["fast_turn_recovery"] = payload
    nested = result.get("result")
    if isinstance(nested, dict):
        nested["fast_turn_recovery"] = payload
        result["result"] = nested
    return result
