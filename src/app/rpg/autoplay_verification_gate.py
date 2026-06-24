"""Deterministic 100-turn autoplay verification gate for RPG Phase 26."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

AUTOPLAY_VERIFICATION_GATE_SOURCE = "phase26_autoplay_verification_gate_v1"
_REQUIRED_SECTIONS = ("narration_prompt", "world", "economy", "combat", "quest", "social")
_DEFAULT_TARGET = 100


def build_autoplay_verification_gate(summary: Mapping[str, object], *, target_turns: int = _DEFAULT_TARGET) -> dict[str, object]:
    """Validate that an autoplay summary proves report coverage and benchmark evidence."""

    rows = _sequence(summary.get("transcript_rows"))
    report_surface = _mapping(summary.get("report_surface"))
    benchmark = _mapping(report_surface.get("benchmark_replay") or summary.get("benchmark_replay"))
    benchmark_payload = _mapping(benchmark.get("benchmark")) if benchmark else {}
    completed = int(summary.get("completed_turns") or report_surface.get("turn_count") or len(rows))
    issues = list(_coverage_issues(rows, report_surface, completed, target_turns))
    issues.extend(_latency_issues(summary, benchmark_payload))
    return {
        "source": AUTOPLAY_VERIFICATION_GATE_SOURCE,
        "target_turns": target_turns,
        "completed_turns": completed,
        "ready": not issues,
        "issues": issues,
        "coverage": {
            "row_count": len(rows),
            "summary_has_report_surface": bool(report_surface),
            "required_sections": list(_REQUIRED_SECTIONS),
        },
        "latency": {
            "blocking_avg_s": _number(summary.get("human_equivalent_avg_s") or benchmark_payload.get("blocking_avg_s")),
            "blocking_p95_s": _number(summary.get("human_equivalent_p95_s") or benchmark_payload.get("blocking_p95_s")),
        },
    }


def attach_autoplay_verification_gate(summary: Mapping[str, object], *, target_turns: int = _DEFAULT_TARGET) -> dict[str, object]:
    result = dict(summary)
    result["autoplay_verification_gate"] = build_autoplay_verification_gate(result, target_turns=target_turns)
    return result


def _coverage_issues(
    rows: Sequence[object],
    report_surface: Mapping[str, object],
    completed: int,
    target_turns: int,
) -> tuple[str, ...]:
    issues: list[str] = []
    if completed < target_turns:
        issues.append("turn_target_not_met")
    if not report_surface:
        issues.append("missing_summary_report_surface")
    for index, row in enumerate(rows, start=1):
        surface = _mapping(_mapping(row).get("report_surface"))
        sections = _mapping(surface.get("sections"))
        for section in _REQUIRED_SECTIONS:
            if section not in sections:
                issues.append(f"turn_{index}_missing_section:{section}")
    return tuple(issues[:25])


def _latency_issues(summary: Mapping[str, object], benchmark: Mapping[str, object]) -> tuple[str, ...]:
    avg = _number(summary.get("human_equivalent_avg_s") or benchmark.get("blocking_avg_s"))
    p95 = _number(summary.get("human_equivalent_p95_s") or benchmark.get("blocking_p95_s"))
    if avg is None and p95 is None:
        return ("missing_latency_evidence",)
    return ()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
