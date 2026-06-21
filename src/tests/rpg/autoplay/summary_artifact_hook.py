"""Helpers for adding setup status to autoplay summary artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.rpg.autoplay.setup_summary import attach_setup_summary
from tests.rpg.autoplay.wizard_new_game_validation import build_wizard_new_game_validation


def _safe_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _turn_rows(summary: Mapping[str, object]) -> list[dict[str, Any]]:
    rows = summary.get("transcript_rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [_safe_dict(row) for row in rows if isinstance(row, Mapping)]


def _last_state(summary: Mapping[str, object]) -> dict[str, Any]:
    for row in reversed(_turn_rows(summary)):
        result = _safe_dict(row.get("turn_result"))
        state = _safe_dict(result.get("simulation_state"))
        if state:
            return state
    return {}


def _summary_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "autoplay-summary.json"


def _turn_count(summary: Mapping[str, object], provided: int | None) -> int | None:
    if provided is not None:
        return provided
    value = summary.get("turns_executed")
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _promote_action_context(summary: dict[str, Any]) -> bool:
    rows = summary.get("transcript_rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return False
    changed = False
    updated: list[dict[str, Any]] = []
    for raw_row in rows:
        row = _safe_dict(raw_row)
        result = _safe_dict(row.get("turn_result"))
        applied = result.get("autoplay_action_text")
        if applied:
            row["player_action"] = str(applied)
            row["autoplay_action_context_applied"] = bool(result.get("autoplay_action_context_applied", True))
            changed = True
        updated.append(row)
    if changed:
        summary["transcript_rows"] = updated
    return changed


def _write_transcript_rows(output_dir: str | Path, rows: object) -> None:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return
    path = Path(output_dir) / "autoplay-transcript.json"
    path.write_text(json.dumps(list(rows), sort_keys=True), encoding="utf-8")


def attach_summary_artifact_status(output_dir: str | Path, *, turns_requested: int | None = None) -> dict[str, Any]:
    path = _summary_path(output_dir)
    try:
        summary = _safe_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {"ok": False, "reason": "summary_unavailable", "source": "summary_artifact_status_v1"}
    action_context_changed = _promote_action_context(summary)
    if action_context_changed:
        _write_transcript_rows(output_dir, summary.get("transcript_rows"))
    state = _last_state(summary)
    status = build_wizard_new_game_validation(
        {"simulation_state": state},
        turns_requested=_turn_count(summary, turns_requested),
    )
    summary["setup_validation"] = status
    attach_setup_summary(summary, status)
    path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "status": status.get("status"),
        "action_context_promoted": action_context_changed,
        "source": "summary_artifact_status_v1",
    }
