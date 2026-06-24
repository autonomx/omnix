"""Runtime NPC relationship, dialogue gate, and memory adapters for RPG Phase 23."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.npc_disposition import (
    DispositionDelta,
    NpcDisposition,
    apply_disposition_deltas,
    companion_eligible,
    memory_summary_from_disposition,
    price_adjustment_percent,
)
from app.rpg.social_scenes import (
    SocialSpeakRequest,
    SocialThread,
    apply_speak_decision,
    build_memory_hook,
    decide_npc_speaks,
    social_scene_report,
)

SOCIAL_RUNTIME_SOURCE = "phase23_social_runtime_v1"


def build_social_runtime_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Build runtime relationship/social-scene metadata from resolved inputs."""

    dispositions = _dispositions(turn_result)
    deltas = tuple(_delta(raw) for raw in _sequence(turn_result.get("disposition_deltas")) if isinstance(raw, Mapping))
    reports = []
    updated: dict[str, NpcDisposition] = {}
    for npc_id, disposition in dispositions.items():
        next_disposition, report = apply_disposition_deltas(disposition, deltas)
        updated[npc_id] = next_disposition
        reports.append(report.as_dict())
    thread = _thread(turn_result)
    requests = tuple(_request(raw, thread.thread_id) for raw in _sequence(turn_result.get("speak_requests")) if isinstance(raw, Mapping))
    decisions = tuple(decide_npc_speaks(thread, request) for request in requests)
    next_thread = thread
    for decision in decisions:
        next_thread = apply_speak_decision(next_thread, decision)
    hooks = tuple(_memory_hook(raw) for raw in _sequence(turn_result.get("memory_hooks")) if isinstance(raw, Mapping))
    issues = tuple(_social_issues(updated, requests, hooks))
    return {
        "source": SOCIAL_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "disposition_reports": reports,
        "npc_memory_summaries": {npc_id: memory_summary_from_disposition(item) for npc_id, item in sorted(updated.items())},
        "companion_eligible": {npc_id: companion_eligible(item) for npc_id, item in sorted(updated.items())},
        "price_adjustment_percent": {npc_id: price_adjustment_percent(item) for npc_id, item in sorted(updated.items())},
        "social_scene": social_scene_report(next_thread, decisions),
        "memory_hooks": [hook.as_dict() for hook in hooks],
    }


def _dispositions(turn_result: Mapping[str, object]) -> dict[str, NpcDisposition]:
    raw_items = _sequence(turn_result.get("npc_dispositions"))
    result: dict[str, NpcDisposition] = {}
    for raw in raw_items:
        if isinstance(raw, Mapping):
            npc_id = str(raw.get("npc_id") or raw.get("id") or "npc")
            values = _mapping(raw.get("values"))
            result[npc_id] = NpcDisposition(npc_id, values)  # type: ignore[arg-type]
    if not result:
        for raw in _sequence(turn_result.get("npc_ids")):
            result[str(raw)] = NpcDisposition.neutral(str(raw))
    return result


def _delta(raw: Mapping[str, object]) -> DispositionDelta:
    return DispositionDelta(
        npc_id=str(raw.get("npc_id") or "npc"),
        axis=str(raw.get("axis") or "trust"),  # type: ignore[arg-type]
        amount=int(raw.get("amount") or 0),
        reason=str(raw.get("reason") or "resolved_event"),
        source_event_id=str(raw.get("source_event_id") or "event"),
    )


def _thread(turn_result: Mapping[str, object]) -> SocialThread:
    raw = _mapping(turn_result.get("social_thread"))
    return SocialThread(
        thread_id=str(raw.get("thread_id") or "runtime-thread"),
        kind=str(raw.get("kind") or "directed"),  # type: ignore[arg-type]
        participants=tuple(str(item) for item in _sequence(raw.get("participants"))),
        active=bool(raw.get("active", True)),
        ambient_budget=int(raw.get("ambient_budget") or 0),
        last_speaker_id=str(raw.get("last_speaker_id")) if raw.get("last_speaker_id") else None,
    )


def _request(raw: Mapping[str, object], default_thread_id: str) -> SocialSpeakRequest:
    return SocialSpeakRequest(
        npc_id=str(raw.get("npc_id") or "npc"),
        thread_id=str(raw.get("thread_id") or default_thread_id),
        directly_addressed=bool(raw.get("directly_addressed", False)),
        urgent_reaction=bool(raw.get("urgent_reaction", False)),
        relationship_trigger=bool(raw.get("relationship_trigger", False)),
        player_is_leaving=bool(raw.get("player_is_leaving", False)),
    )


def _memory_hook(raw: Mapping[str, object]):
    return build_memory_hook(
        str(raw.get("kind") or "clue"),  # type: ignore[arg-type]
        source_event_id=str(raw.get("source_event_id") or "event"),
        npc_ids=tuple(str(item) for item in _sequence(raw.get("npc_ids"))),
        fact=str(raw.get("fact") or ""),
    )


def _social_issues(
    dispositions: Mapping[str, NpcDisposition],
    requests: Sequence[SocialSpeakRequest],
    hooks: Sequence[object],
) -> tuple[str, ...]:
    issues: list[str] = []
    if not dispositions:
        issues.append("missing_npc_dispositions")
    if not requests:
        issues.append("missing_speak_requests")
    for hook in hooks:
        if not getattr(hook, "fact", ""):
            issues.append("empty_memory_hook_fact")
    return tuple(issues)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
