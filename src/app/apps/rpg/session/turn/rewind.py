"""Rewinding (RQ-5.7; docs/rpg/design/rewind.md): undo the last turn, or return to a save point, as a new revision.

An undo goes back to before the hero's last turn, past the world's ticks and the game's own upgrades in between,
and past earlier rewinds to where each one returned (so undoing twice goes two turns back). The earlier document is
rebuilt from the campaign's history and checked against it, and its game is put back as a new revision
(``RevisionRestored``); history is never rewritten. A hardcore campaign cannot rewind.
"""
from __future__ import annotations

from typing import Any, Mapping

MAX_SAVE_POINTS = 20


def undo_target(history: list[Mapping[str, Any]], current_revision: int) -> int | None:
    """The revision before the hero's last turn, walking back from ``current_revision`` (``history`` newest first)."""
    cursor = int(current_revision)
    for turn in history:
        if int(turn["resulting_revision"]) != cursor:
            continue  # a turn of a line a rewind left behind
        command = dict(turn.get("command") or {})
        if command.get("turn_kind") == "rewind":
            cursor = int(command.get("restored_revision") or 0)  # the moment it returned to
        elif command.get("turn_kind") in {"world_tick", "system"} or command.get("kind") == "system" or not str(
                command.get("player_input") or "").strip():
            cursor = int(turn["expected_revision"])  # the world's ticks and the game's upgrades are not the hero's
        else:
            return int(turn["expected_revision"])
    return None


__all__ = ["MAX_SAVE_POINTS", "undo_target"]
