"""Versioned, idempotent migrations for durable RPG session payloads."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

_CURRENT_SCHEMA_VERSION = 5
_INTERACTION_TIMELINE_VERSION = "rpg_interaction_timeline_v1"
_MAX_INTERACTIONS = 50
_LEGACY_TRANSCRIPT_KEYS = (
    "transcript",
    "dialogue_history",
    "conversation_history",
    "dialogue_log",
)


def migrate_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a migrated copy without changing authoritative turn mechanics."""

    root = deepcopy(payload) if isinstance(payload, dict) else {}
    if "save_version" in root and isinstance(root.get("session"), dict):
        root["session"] = _migrate_session(root["session"])
        return root
    return _migrate_session(root)


def _migrate_session(session: dict[str, Any]) -> dict[str, Any]:
    session = deepcopy(session) if isinstance(session, dict) else {}
    manifest = _dict(session.get("manifest"))
    manifest["id"] = _text(manifest.get("id") or manifest.get("session_id")) or "session:unknown"
    manifest.setdefault("session_id", manifest["id"])

    simulation_state = _dict(session.get("simulation_state"))
    runtime_state = _dict(session.get("runtime_state"))
    state = _dict(session.get("state"))
    if not state and simulation_state:
        state = deepcopy(simulation_state)

    simulation_state.setdefault("presentation_state", {})
    simulation_state.setdefault("memory_state", {})
    runtime_state.setdefault("ambient_queue", [])
    runtime_state.setdefault("ambient_seq", 0)
    runtime_state.setdefault("last_idle_tick_at", "")
    runtime_state.setdefault("last_player_turn_at", "")
    runtime_state.setdefault("idle_streak", 0)
    runtime_state.setdefault("ambient_cooldowns", {})
    runtime_state.setdefault("recent_ambient_ids", [])
    runtime_state.setdefault("pending_interrupt", None)
    runtime_state.setdefault("subscription_state", {"last_polled_seq": 0})
    runtime_state.setdefault("ambient_metrics", {"emitted": 0, "suppressed": 0, "coalesced": 0})
    session["simulation_state"] = simulation_state
    session["runtime_state"] = runtime_state
    session["state"] = state

    _migrate_legacy_interactions(session)
    manifest["schema_version"] = _CURRENT_SCHEMA_VERSION
    session["manifest"] = manifest
    return session


def _migrate_legacy_interactions(session: dict[str, Any]) -> None:
    runtime = _dict(session.get("runtime_state"))
    timeline = _dict(runtime.get("interaction_timeline"))
    existing_events = [deepcopy(item) for item in _list(timeline.get("events")) if isinstance(item, dict)]

    if existing_events:
        events = _normalize_existing_events(existing_events)
        migrated_count = int(_dict(runtime.get("legacy_interaction_migration")).get("migrated_count") or 0)
    else:
        rows, source = _legacy_transcript_rows(session)
        events = _legacy_rows_to_events(rows)
        migrated_count = len(events)
        if rows:
            runtime["legacy_interaction_migration"] = {
                "format_version": "rpg_legacy_interaction_migration_v1",
                "source": source,
                "migrated_count": migrated_count,
                "completed": True,
            }
        _remove_legacy_transcripts(session)

    events = events[-_MAX_INTERACTIONS:]
    max_sequence = max((_safe_int(item.get("sequence")) for item in events), default=0)
    last_sequence = max(
        _safe_int(runtime.get("interaction_seq")),
        _safe_int(timeline.get("last_sequence")),
        max_sequence,
    )
    state_revision = max(
        _safe_int(runtime.get("state_revision")),
        _safe_int(timeline.get("state_revision")),
        max_sequence,
    )
    timeline.update(
        {
            "format_version": _INTERACTION_TIMELINE_VERSION,
            "last_sequence": last_sequence,
            "state_revision": state_revision,
            "events": events,
        }
    )
    runtime["interaction_seq"] = last_sequence
    runtime["state_revision"] = state_revision
    runtime["interaction_timeline"] = timeline
    runtime["recent_interactions"] = deepcopy(events[-12:])
    if events:
        runtime["last_interaction"] = deepcopy(events[-1])
    if migrated_count and "legacy_interaction_migration" not in runtime:
        runtime["legacy_interaction_migration"] = {
            "format_version": "rpg_legacy_interaction_migration_v1",
            "migrated_count": migrated_count,
            "completed": True,
        }
    session["runtime_state"] = runtime


def _legacy_transcript_rows(session: dict[str, Any]) -> tuple[list[Any], str]:
    containers = (
        ("runtime_state", _dict(session.get("runtime_state"))),
        ("session", session),
        ("simulation_state", _dict(session.get("simulation_state"))),
        ("state", _dict(session.get("state"))),
    )
    for container_name, container in containers:
        for key in _LEGACY_TRANSCRIPT_KEYS:
            value = container.get(key)
            if isinstance(value, list) and value:
                return list(value), f"{container_name}.{key}"
    return [], ""


def _legacy_rows_to_events(rows: list[Any]) -> list[dict[str, Any]]:
    interactions: list[dict[str, Any]] = []
    pending_player = ""
    for raw in rows:
        if isinstance(raw, dict):
            event = _legacy_dict_event(raw, len(interactions) + 1)
            if event:
                interactions.append(event)
            continue
        text = _text(raw)
        if not text:
            continue
        speaker, content = _split_speaker(text)
        if _normalize(speaker) in {"you", "player", "hero"}:
            pending_player = content
            continue
        interactions.append(
            _build_legacy_event(
                sequence=len(interactions) + 1,
                player_input=pending_player,
                speaker=speaker,
                npc_line=content if speaker else "",
                narration=content if not speaker else "",
                created_at="",
                source={},
            )
        )
        pending_player = ""
    if pending_player:
        interactions.append(
            _build_legacy_event(
                sequence=len(interactions) + 1,
                player_input=pending_player,
                speaker="",
                npc_line="",
                narration="",
                created_at="",
                source={},
            )
        )
    return interactions[-_MAX_INTERACTIONS:]


def _legacy_dict_event(row: dict[str, Any], sequence: int) -> dict[str, Any] | None:
    player_input = _first_text(row, "player_input", "command", "input", "player_text")
    speaker = _first_text(row, "speaker", "npc_name", "actor")
    npc_line = _first_text(row, "npc_line", "response", "output", "reply")
    narration = _first_text(row, "narration", "summary", "scene_text")
    visible = _dict(row.get("visible_response"))
    if visible:
        messages = [item for item in _list(visible.get("messages")) if isinstance(item, dict)]
        if messages and not speaker:
            speaker = _first_text(messages[0], "speaker", "name")
            npc_line = _first_text(messages[0], "text", "line")
        narration = narration or _text(visible.get("narration"))
    if not any((player_input, speaker, npc_line, narration, visible)):
        generic = _text(row.get("text") or row.get("message"))
        if not generic:
            return None
        parsed_speaker, parsed_text = _split_speaker(generic)
        speaker = parsed_speaker
        npc_line = parsed_text if parsed_speaker else ""
        narration = parsed_text if not parsed_speaker else ""
    return _build_legacy_event(
        sequence=sequence,
        player_input=player_input,
        speaker=speaker,
        npc_line=npc_line,
        narration=narration,
        created_at=_first_text(row, "created_at", "timestamp", "time"),
        source=row,
        visible=visible,
    )


def _build_legacy_event(
    *,
    sequence: int,
    player_input: str,
    speaker: str,
    npc_line: str,
    narration: str,
    created_at: str,
    source: dict[str, Any],
    visible: dict[str, Any] | None = None,
) -> dict[str, Any]:
    visible_response = _bounded_visible_response(
        visible or {},
        speaker=speaker,
        npc_line=npc_line,
        narration=narration,
    )
    event = {
        "format_version": _INTERACTION_TIMELINE_VERSION,
        "interaction_id": _text(source.get("interaction_id")) or f"interaction:{sequence}",
        "sequence": sequence,
        "state_revision": max(sequence, _safe_int(source.get("state_revision"))),
        "simulation_tick": _int_or_none(source.get("simulation_tick") or source.get("tick")),
        "turn_id": _text(source.get("turn_id")),
        "submission_id": _text(source.get("submission_id")),
        "trace_id": _text(source.get("trace_id")),
        "kind": _text(source.get("kind")) or ("npc_dialogue" if speaker or npc_line else "player_turn"),
        "stateful": source.get("stateful") if isinstance(source.get("stateful"), bool) else None,
        "player_input": _clip(player_input, 2_000),
        "visible_response": visible_response,
        "speaker_id": _text(source.get("speaker_id") or source.get("npc_id")),
        "speaker": _clip(speaker, 256),
        "npc_line": _clip(npc_line, 2_000),
        "narration": _clip(narration, 2_000),
        "action_type": _text(source.get("action_type")),
        "semantic_family": _text(source.get("semantic_family")),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "migrated_from_legacy_transcript": True,
    }
    return _drop_empty(event)


def _bounded_visible_response(
    visible: dict[str, Any],
    *,
    speaker: str,
    npc_line: str,
    narration: str,
) -> dict[str, Any]:
    messages = []
    for raw in _list(visible.get("messages"))[:4]:
        if not isinstance(raw, dict):
            continue
        messages.append(
            _drop_empty(
                {
                    "kind": _text(raw.get("kind")) or "npc_dialogue",
                    "speaker_id": _text(raw.get("speaker_id")),
                    "speaker": _clip(raw.get("speaker"), 256),
                    "text": _clip(raw.get("text"), 2_000),
                }
            )
        )
    if npc_line and not messages:
        messages.append(
            _drop_empty(
                {
                    "kind": "npc_dialogue",
                    "speaker": _clip(speaker, 256),
                    "text": _clip(npc_line, 2_000),
                }
            )
        )
    resolved_narration = _clip(visible.get("narration") or narration, 2_000)
    plain = _clip(visible.get("plain_text"), 4_000)
    if not plain:
        parts = [resolved_narration]
        if speaker and npc_line:
            parts.append(f'{speaker}: "{npc_line}"')
        elif npc_line:
            parts.append(npc_line)
        plain = "\n\n".join(part for part in parts if part)
    return _drop_empty(
        {
            "format_version": _text(visible.get("format_version")) or "rpg_visible_response_v1",
            "narration": resolved_narration,
            "messages": messages,
            "plain_text": _clip(plain, 4_000),
        }
    )


def _normalize_existing_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(events[-_MAX_INTERACTIONS:], start=1):
        event = deepcopy(raw)
        sequence = _safe_int(event.get("sequence")) or index
        event["format_version"] = _INTERACTION_TIMELINE_VERSION
        event["sequence"] = sequence
        event["interaction_id"] = _text(event.get("interaction_id")) or f"interaction:{sequence}"
        event["state_revision"] = max(sequence, _safe_int(event.get("state_revision")))
        normalized.append(event)
    normalized.sort(key=lambda item: _safe_int(item.get("sequence")))
    return normalized


def _remove_legacy_transcripts(session: dict[str, Any]) -> None:
    for container_key in ("runtime_state", "simulation_state", "state"):
        container = _dict(session.get(container_key))
        for key in _LEGACY_TRANSCRIPT_KEYS:
            container.pop(key, None)
        session[container_key] = container
    for key in _LEGACY_TRANSCRIPT_KEYS:
        session.pop(key, None)


def _split_speaker(text: str) -> tuple[str, str]:
    if ":" not in text:
        return "", text
    speaker, content = text.split(":", 1)
    speaker = speaker.strip()
    if not speaker or len(speaker.split()) > 4:
        return "", text
    return speaker, content.strip()


def _first_text(value: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _text(value.get(key))
        if text:
            return text
    return ""


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    return _int_or_none(value) or 0


def _clip(value: Any, limit: int) -> str:
    return _text(value)[:limit]


def _normalize(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != "" and item != [] and item != {}
    }


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
