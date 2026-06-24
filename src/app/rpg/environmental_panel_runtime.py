"""Report-panel adapter for environmental scene memory and activity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.environmental_narration_runtime import build_environmental_narration_report

ENVIRONMENTAL_PANEL_SOURCE = "phase35_environmental_panel_runtime_v1"


def build_environmental_panel_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Build report-surface metadata for the environmental scene panel."""

    narration = build_environmental_narration_report(turn_result)
    memory = _mapping(narration.get("state_memory"))
    activity = _mapping(narration.get("living_activity"))
    changed_fields = tuple(str(item.get("field") or "") for item in _mappings(memory.get("changed_fields")))
    perceptual_fields = tuple(str(item.get("field") or "") for item in _mappings(memory.get("perceptual_changes")))
    opportunities = tuple(str(item) for item in _sequence(activity.get("opportunities")))
    cues = _panel_cues(changed_fields, perceptual_fields, opportunities)
    issues = _issues(narration, activity)
    return {
        "source": ENVIRONMENTAL_PANEL_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "title": "Environmental scene",
        "badges": _badges(narration, activity, changed_fields),
        "triggers": tuple(str(item) for item in _sequence(narration.get("triggers"))),
        "changed_fields": changed_fields,
        "perceptual_fields": perceptual_fields,
        "visible_activity": list(_mappings(activity.get("visible_activity"))),
        "opportunities": opportunities,
        "panel_cues": cues,
    }


def attach_environmental_panel_to_summary(summary: Mapping[str, object]) -> dict[str, object]:
    """Attach environmental panel payloads to every transcript row."""

    result = dict(summary)
    rows: list[dict[str, object]] = []
    for raw in _sequence(summary.get("transcript_rows")):
        if isinstance(raw, Mapping):
            row = dict(raw)
            row["environmental_panel"] = build_environmental_panel_report(_mapping(raw.get("turn_result")) or raw)
            rows.append(row)
    result["transcript_rows"] = rows
    result["environmental_panel"] = _aggregate(rows)
    return result


def _badges(
    narration: Mapping[str, object],
    activity: Mapping[str, object],
    changed_fields: Sequence[str],
) -> tuple[str, ...]:
    badges = [str(activity.get("intensity") or "quiet")]
    if narration.get("should_generate"):
        badges.append("scene_intro")
    if changed_fields:
        badges.append("changed")
    if activity.get("opportunities"):
        badges.append("opportunities")
    return tuple(dict.fromkeys(item for item in badges if item))


def _panel_cues(
    changed_fields: Sequence[str],
    perceptual_fields: Sequence[str],
    opportunities: Sequence[str],
) -> tuple[str, ...]:
    cues: list[str] = []
    if changed_fields:
        cues.append("Changed: " + ", ".join(changed_fields))
    if perceptual_fields:
        cues.append("Perceptual shift: " + ", ".join(perceptual_fields))
    if opportunities:
        cues.append("Opportunities: " + ", ".join(opportunities))
    return tuple(cues)


def _issues(narration: Mapping[str, object], activity: Mapping[str, object]) -> tuple[str, ...]:
    issues = [str(item) for item in _sequence(narration.get("issues"))]
    issues.extend(str(item) for item in _sequence(activity.get("issues")))
    return tuple(dict.fromkeys(item for item in issues if item))


def _aggregate(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    trigger_counts: dict[str, int] = {}
    changed_counts: dict[str, int] = {}
    opportunity_counts: dict[str, int] = {}
    ready_count = 0
    for row in rows:
        panel = _mapping(row.get("environmental_panel"))
        if panel.get("ready") is True:
            ready_count += 1
        for trigger in _sequence(panel.get("triggers")):
            key = str(trigger)
            trigger_counts[key] = trigger_counts.get(key, 0) + 1
        for field in _sequence(panel.get("changed_fields")):
            key = str(field)
            changed_counts[key] = changed_counts.get(key, 0) + 1
        for opportunity in _sequence(panel.get("opportunities")):
            key = str(opportunity)
            opportunity_counts[key] = opportunity_counts.get(key, 0) + 1
    return {
        "source": ENVIRONMENTAL_PANEL_SOURCE,
        "turn_count": len(rows),
        "ready_turn_count": ready_count,
        "trigger_counts": dict(sorted(trigger_counts.items())),
        "changed_field_counts": dict(sorted(changed_counts.items())),
        "opportunity_counts": dict(sorted(opportunity_counts.items())),
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _mappings(value: object) -> tuple[Mapping[str, object], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))
