"""Compact priority-context helpers for RPG autoplay setup state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .weight_context import action_with_weight_note

_PRIORITY_KEY = "_".join(("active", "goals"))
_COMPILED_KEY = "_".join(("compiled", "goals"))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_rows(value: object) -> list[dict[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_mapping(item) for item in value if isinstance(item, Mapping)]
    return []


def _rows(state: Mapping[str, object]) -> list[dict[str, Any]]:
    direct = _sequence_rows(state.get(_PRIORITY_KEY))
    if direct:
        return direct
    bootstrap = _mapping(state.get("bootstrap_snapshot"))
    from_bootstrap = _sequence_rows(bootstrap.get(_PRIORITY_KEY))
    if from_bootstrap:
        return from_bootstrap
    compiled = _mapping(state.get("compiled_genesis_snapshot"))
    return _sequence_rows(compiled.get(_COMPILED_KEY))


def primary_priority_context(state: Mapping[str, object]) -> dict[str, Any]:
    rows = [row for row in _rows(state) if str(row.get("status") or "active") == "active"]
    rows.sort(key=lambda row: int(row.get("priority") or 0), reverse=True)
    if not rows:
        return {"ok": False, "source": "priority_context_v1", "suffix": ""}
    row = rows[0]
    label = str(row.get("id") or "objective").replace("_", " ")
    return {
        "ok": True,
        "source": "priority_context_v1",
        "id": row.get("id"),
        "origin": row.get("source"),
        "priority": int(row.get("priority") or 0),
        "suffix": f" while focusing on {label}",
    }


def apply_priority_context(base_text: str, state: Mapping[str, object]) -> str:
    context = primary_priority_context(state)
    suffix = str(context.get("suffix") or "")
    return f"{base_text}{suffix}" if suffix else base_text


def autoplay_action_text(turn_index: int, state: Mapping[str, object]) -> str:
    """Return the standard autoplay turn action with compiled setup context applied."""

    priority_text = apply_priority_context(f"continue turn {int(turn_index)}", state)
    return action_with_weight_note(priority_text, state)
