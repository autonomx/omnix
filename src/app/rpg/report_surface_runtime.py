"""Unified runtime report surface for RPG Phase 25."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from app.rpg.benchmark_replay_runtime import build_benchmark_replay_report
from app.rpg.combat_runtime import build_combat_runtime_report
from app.rpg.economy_runtime import build_economy_runtime_report
from app.rpg.narration_prompt_runtime import build_narration_prompt_runtime_metadata
from app.rpg.quest_runtime import build_quest_runtime_report
from app.rpg.social_runtime import build_social_runtime_report
from app.rpg.world_runtime import build_world_runtime_report

REPORT_SURFACE_RUNTIME_SOURCE = "phase25_report_surface_runtime_v1"
_SECTION_BUILDERS = (
    ("narration_prompt", build_narration_prompt_runtime_metadata),
    ("world", build_world_runtime_report),
    ("economy", build_economy_runtime_report),
    ("combat", build_combat_runtime_report),
    ("quest", build_quest_runtime_report),
    ("social", build_social_runtime_report),
)


def attach_report_surface_to_row(
    row: Mapping[str, object],
    *,
    previous_rows: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Attach all runtime adapter sections to a transcript row."""

    result = dict(row)
    turn_result = _mapping(row.get("turn_result")) or row
    action = str(row.get("player_action") or turn_result.get("autoplay_action_text") or "")
    recent = tuple(str(item.get("narration") or "") for item in previous_rows if isinstance(item, Mapping))
    sections: dict[str, object] = {}
    issues: dict[str, list[str]] = {}
    for name, builder in _SECTION_BUILDERS:
        payload = _build_section(name, builder, turn_result, action, recent)
        sections[name] = payload
        payload_issues = [str(item) for item in _sequence(_mapping(payload).get("issues"))]
        if payload_issues:
            issues[name] = payload_issues
    result["report_surface"] = {
        "source": REPORT_SURFACE_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": issues,
        "sections": sections,
    }
    return result


def attach_report_surface_to_summary(summary: Mapping[str, object], *, persist: bool = False) -> dict[str, object]:
    """Decorate autoplay summary/transcript artifacts with all runtime sections."""

    result = dict(summary)
    rows: list[dict[str, object]] = []
    for raw in _sequence(summary.get("transcript_rows")):
        if isinstance(raw, Mapping):
            rows.append(attach_report_surface_to_row(raw, previous_rows=rows))
    result["transcript_rows"] = rows
    result["report_surface"] = _aggregate_rows(rows)
    if persist:
        _persist_summary_artifacts(result)
    return result


def _build_section(name: str, builder, turn_result: Mapping[str, object], action: str, recent: Sequence[str]) -> object:
    if name == "narration_prompt":
        return builder(turn_result, player_action=action, recent_narrations=recent)
    return builder(turn_result)


def _aggregate_rows(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    section_issue_counts: dict[str, dict[str, int]] = {}
    ready_count = 0
    for row in rows:
        surface = _mapping(row.get("report_surface"))
        if surface.get("ready") is True:
            ready_count += 1
        for section, issues in _mapping(surface.get("issues")).items():
            counts = section_issue_counts.setdefault(str(section), {})
            for issue in _sequence(issues):
                key = str(issue)
                counts[key] = counts.get(key, 0) + 1
    return {
        "source": REPORT_SURFACE_RUNTIME_SOURCE,
        "turn_count": len(rows),
        "ready_turn_count": ready_count,
        "section_issue_counts": {key: dict(sorted(value.items())) for key, value in sorted(section_issue_counts.items())},
        "sections": [name for name, _ in _SECTION_BUILDERS],
        "benchmark_replay": build_benchmark_replay_report({**dict(rows=()), **dict(transcript_rows=list(rows))}),
    }


def _persist_summary_artifacts(summary: Mapping[str, object]) -> None:
    paths = _mapping(summary.get("artifact_paths"))
    for key in ("summary", "transcript"):
        path = paths.get(key)
        if not path:
            continue
        payload: object = summary if key == "summary" else summary.get("transcript_rows", [])
        Path(str(path)).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
