"""Runtime narration quality and prompt profile adapters for RPG Phase 18."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from app.rpg.narration_quality import build_safe_rewrite_contract, evaluate_narration_quality
from app.rpg.prompt_profiles import (
    RpgPromptProfile,
    RpgPromptTask,
    default_rpg_prompt_profile_registry,
    rpg_prompt_profile_debug_payload,
    validate_rpg_prompt_profile_registry,
)

NARRATION_PROMPT_RUNTIME_SOURCE = "phase18_narration_prompt_runtime_v1"
_DEFAULT_TASKS: tuple[RpgPromptTask, ...] = (
    "intent_classification",
    "narration",
    "quality_rewrite",
    "grounding_audit",
)


def build_narration_prompt_runtime_metadata(
    turn_result: Mapping[str, object],
    *,
    player_action: str,
    recent_narrations: Sequence[str] = (),
    registry: Mapping[RpgPromptTask, RpgPromptProfile] | None = None,
    prompt_tasks: Sequence[RpgPromptTask] = _DEFAULT_TASKS,
) -> dict[str, object]:
    """Build presentation-only narration/prompt runtime metadata for one turn."""

    state_facts = _state_facts(turn_result)
    narration = _narration(turn_result)
    quality = evaluate_narration_quality(
        narration,
        recent_texts=tuple(str(item) for item in recent_narrations)[-5:],
    )
    rewrite_contract = None
    if quality.should_request_rewrite:
        rewrite_contract = build_safe_rewrite_contract(
            narration,
            state_facts=state_facts,
            quality_report=quality,
        )
    active_registry = registry or default_rpg_prompt_profile_registry()
    profile_issues = validate_rpg_prompt_profile_registry(active_registry)
    profile_payloads = tuple(
        rpg_prompt_profile_debug_payload(
            task,
            registry=active_registry,
            status="phase18_runtime_selected",
        )
        for task in tuple(prompt_tasks)
    )
    issues = tuple(_runtime_issues(quality.as_dict(), profile_issues))
    return {
        "source": NARRATION_PROMPT_RUNTIME_SOURCE,
        "player_action": player_action,
        "narration_quality": quality.as_dict(),
        "rewrite_contract": rewrite_contract,
        "prompt_profiles": [dict(payload) for payload in profile_payloads],
        "prompt_profile_issues": list(profile_issues),
        "ready": not issues,
        "issues": list(issues),
    }


def attach_narration_prompt_runtime_to_row(
    row: Mapping[str, object],
    *,
    previous_rows: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Decorate one transcript row with Phase 18 runtime metadata."""

    result = dict(row)
    turn_result = _mapping(row.get("turn_result"))
    player_action = str(row.get("player_action") or turn_result.get("autoplay_action_text") or "")
    recent = tuple(str(item.get("narration") or "") for item in previous_rows if isinstance(item, Mapping))
    result["narration_prompt_runtime"] = build_narration_prompt_runtime_metadata(
        turn_result or row,
        player_action=player_action,
        recent_narrations=recent,
    )
    return result


def attach_narration_prompt_runtime_to_summary(
    summary: Mapping[str, object],
    *,
    persist: bool = False,
) -> dict[str, object]:
    """Attach Phase 18 metadata to autoplay summaries and transcript artifacts."""

    result = dict(summary)
    rows: list[dict[str, object]] = []
    for raw in _sequence(summary.get("transcript_rows")):
        if isinstance(raw, Mapping):
            rows.append(attach_narration_prompt_runtime_to_row(raw, previous_rows=rows))
    result["transcript_rows"] = rows
    result["narration_prompt_runtime"] = _aggregate_rows(rows)
    if persist:
        _persist_summary_artifacts(result)
    return result


def _aggregate_rows(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    issue_counts: dict[str, int] = {}
    rewrite_count = 0
    ready_count = 0
    for row in rows:
        payload = _mapping(row.get("narration_prompt_runtime"))
        if payload.get("ready") is True:
            ready_count += 1
        quality = _mapping(payload.get("narration_quality"))
        if quality.get("should_request_rewrite"):
            rewrite_count += 1
        for issue in _sequence(payload.get("issues")):
            issue_counts[str(issue)] = issue_counts.get(str(issue), 0) + 1
    return {
        "source": NARRATION_PROMPT_RUNTIME_SOURCE,
        "turn_count": len(rows),
        "ready_turn_count": ready_count,
        "rewrite_recommended_count": rewrite_count,
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def _runtime_issues(quality_payload: Mapping[str, object], profile_issues: Sequence[str]) -> tuple[str, ...]:
    issues = list(str(item) for item in profile_issues)
    if quality_payload.get("should_request_rewrite"):
        issues.append("narration_rewrite_required")
    return tuple(issues)


def _narration(turn_result: Mapping[str, object]) -> str:
    payload = _mapping(turn_result.get("narration_payload"))
    return str(turn_result.get("narration") or payload.get("text") or "")


def _state_facts(turn_result: Mapping[str, object]) -> Mapping[str, object]:
    facts = _mapping(turn_result.get("state_facts"))
    if facts:
        return facts
    return _mapping(turn_result.get("simulation_state") or turn_result.get("state"))


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _persist_summary_artifacts(summary: Mapping[str, object]) -> None:
    paths = _mapping(summary.get("artifact_paths"))
    for key in ("summary", "transcript"):
        path = paths.get(key)
        if not path:
            continue
        payload: object = summary if key == "summary" else summary.get("transcript_rows", [])
        Path(str(path)).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
