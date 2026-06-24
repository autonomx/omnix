"""Environmental autoplay verification helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

ENVIRONMENTAL_AUTOPLAY_VERIFICATION_SOURCE = "phase39_environmental_autoplay_verification_v1"


def build_environmental_autoplay_verification(summary: Mapping[str, object]) -> dict[str, object]:
    rows = [row for row in _sequence(summary.get("transcript_rows")) if isinstance(row, Mapping)]
    trigger_counts: dict[str, int] = {}
    changed_counts: dict[str, int] = {}
    opportunity_counts: dict[str, int] = {}
    panel_rows = 0
    narration_rows = 0
    carried_rows = 0
    visible_rows = 0
    for row in rows:
        sections = _mapping(_mapping(row.get("report_surface")).get("sections"))
        narration = _mapping(row.get("environmental_narration")) or _mapping(sections.get("environmental_narration"))
        panel = _mapping(row.get("environmental_panel")) or _mapping(sections.get("environmental_panel"))
        trace = _mapping(row.get("env_scene_trace"))
        if narration:
            narration_rows += 1
            _count_values(trigger_counts, narration.get("triggers"))
            memory = _mapping(narration.get("state_memory"))
            for change in _sequence(memory.get("changed_fields")):
                field = str(_mapping(change).get("field") or "")
                if field:
                    changed_counts[field] = changed_counts.get(field, 0) + 1
        if panel:
            panel_rows += 1
            _count_values(trigger_counts, panel.get("triggers"))
            _count_values(changed_counts, panel.get("changed_fields"))
            _count_values(opportunity_counts, panel.get("opportunities"))
            if _sequence(panel.get("visible_activity")):
                visible_rows += 1
        carried_rows += int(trace.get("prior_carried") is True)
    issues = list(_issues(rows, panel_rows, narration_rows, trigger_counts, changed_counts, visible_rows))
    return {
        "source": ENVIRONMENTAL_AUTOPLAY_VERIFICATION_SOURCE,
        "ready": not issues,
        "issues": issues,
        "turn_count": len(rows),
        "environmental_panel_rows": panel_rows,
        "environmental_narration_rows": narration_rows,
        "carried_previous_scene_count": carried_rows,
        "visible_activity_rows": visible_rows,
        "trigger_counts": dict(sorted(trigger_counts.items())),
        "changed_field_counts": dict(sorted(changed_counts.items())),
        "opportunity_counts": dict(sorted(opportunity_counts.items())),
    }


def attach_environmental_autoplay_verification(summary: Mapping[str, object]) -> dict[str, object]:
    result = dict(summary)
    result["environmental_autoplay_verification"] = build_environmental_autoplay_verification(summary)
    return result


def _issues(
    rows: Sequence[Mapping[str, object]],
    panel_rows: int,
    narration_rows: int,
    trigger_counts: Mapping[str, int],
    changed_counts: Mapping[str, int],
    visible_rows: int,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not rows:
        issues.append("no_transcript_rows")
    if rows and not panel_rows:
        issues.append("missing_environmental_panel_rows")
    if rows and not narration_rows:
        issues.append("missing_environmental_narration_rows")
    if rows and not trigger_counts:
        issues.append("missing_environmental_triggers")
    if len(rows) >= 2 and not changed_counts:
        issues.append("missing_environmental_change_evidence")
    if rows and not visible_rows:
        issues.append("missing_visible_activity_rows")
    return tuple(issues)


def _count_values(counts: dict[str, int], values: object) -> None:
    for value in _sequence(values):
        key = str(value)
        if key:
            counts[key] = counts.get(key, 0) + 1


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
