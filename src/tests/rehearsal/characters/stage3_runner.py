"""Orchestration for the Character Mode Stage 3 write-memory pilot."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .stage2_fixtures import ensure_character, memory_record_ids, snapshot_item_ids
from .stage3_contracts import (
    Stage3Check,
    Stage3Checkpoint,
    Stage3Metrics,
    Stage3PrepareConfig,
    Stage3Report,
    decision,
    duration_ms,
    marker,
    marker_hash,
    marker_memory,
    safe_error,
    utcnow,
)
from .stage3_http import Stage3Gateway


def _check(
    checks: list[Stage3Check],
    check_id: str,
    operation: Callable[[], tuple[Any, str, dict[str, Any]]],
) -> Any:
    started = time.perf_counter()
    try:
        value, summary, observed = operation()
    except Exception as exc:
        checks.append(
            Stage3Check(
                id=check_id,
                status="fail",
                summary=safe_error(exc),
                duration_ms=duration_ms(started),
            )
        )
        return None
    checks.append(
        Stage3Check(
            id=check_id,
            status="pass",
            summary=summary,
            duration_ms=duration_ms(started),
            observed=observed,
        )
    )
    return value


def _report(
    config: Stage3PrepareConfig,
    checks: list[Stage3Check],
    metrics: Stage3Metrics,
    *,
    mode: str,
    session_id: str | None,
    checkpoint_path: str | Path | None = None,
) -> Stage3Report:
    return Stage3Report(
        generated_at=utcnow(),
        mode=mode,  # type: ignore[arg-type]
        decision=decision(checks),
        base_url=config.base_url,
        run_id=config.run_id,
        maya_character_id=config.maya_character_id,
        maya_rw_session_id=session_id,
        checks=checks,
        metrics=metrics,
        checkpoint_path=str(checkpoint_path) if checkpoint_path else None,
        notes=[
            "Reports contain IDs, hashes, counts, policies, and timings only; synthetic memory text and model output are not persisted.",
            "Stage 3 cleanup runs only after restart verification proves records, candidates, and snapshots survived restart.",
        ],
    )


def _health(gateway: Stage3Gateway):
    payload = gateway.health()
    if payload.get("ok") is not True or payload.get("status") != "ready":
        raise RuntimeError("Gateway health endpoint is not ready")
    return payload, "Gateway health endpoint is ready.", {"ready": True}


def _ensure_profiles(gateway: Stage3Gateway, config: Stage3PrepareConfig):
    maya = ensure_character(gateway, config.maya_character_id, "Maya Stage 3")
    alex = ensure_character(gateway, config.alex_character_id, "Alex Stage 3")
    return (
        (maya, alex),
        "Synthetic Maya and Alex Stage 3 profiles are active.",
        {
            "maya_character_id": config.maya_character_id,
            "alex_character_id": config.alex_character_id,
            "maya_profile_version": maya.get("active_version"),
            "alex_profile_version": alex.get("active_version"),
        },
    )


def _create_character_session(
    gateway: Stage3Gateway,
    config: Stage3PrepareConfig,
    *,
    title: str,
    character_id: str,
    read_memory: bool,
    write_memory: bool,
) -> dict[str, Any]:
    return gateway.create_session(
        {
            "title": title,
            "provider_id": config.provider_id,
            "model_id": config.model_id,
            "interaction_mode": "character",
            "character_id": character_id,
            "read_memory": read_memory,
            "write_memory": write_memory,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
        }
    )


def _create_sessions(gateway: Stage3Gateway, config: Stage3PrepareConfig):
    maya_rw = _create_character_session(
        gateway,
        config,
        title="Stage 3 Maya read-write memory pilot",
        character_id=config.maya_character_id,
        read_memory=True,
        write_memory=True,
    )
    maya_write_only = _create_character_session(
        gateway,
        config,
        title="Stage 3 Maya write-only memory control",
        character_id=config.maya_character_id,
        read_memory=False,
        write_memory=True,
    )
    alex_control = _create_character_session(
        gateway,
        config,
        title="Stage 3 Alex owner isolation control",
        character_id=config.alex_character_id,
        read_memory=True,
        write_memory=True,
    )
    for session, expected_character, read_memory, write_memory in (
        (maya_rw, config.maya_character_id, True, True),
        (maya_write_only, config.maya_character_id, False, True),
        (alex_control, config.alex_character_id, True, True),
    ):
        if session.get("interaction_mode") != "character":
            raise RuntimeError("Stage 3 session did not enter Character Mode")
        if session.get("character_id") != expected_character:
            raise RuntimeError("Stage 3 session resolved the wrong character")
        if session.get("read_memory") is not read_memory or session.get("write_memory") is not write_memory:
            raise RuntimeError("Stage 3 session has the wrong memory policy")
        if session.get("shared_memory_access") != "none":
            raise RuntimeError("Stage 3 session enabled shared System Assistant memory")
    return (
        (maya_rw, maya_write_only, alex_control),
        "Stage 3 read-write, write-only, and isolation sessions are active.",
        {
            "maya_rw_session_id": maya_rw.get("id"),
            "maya_write_only_session_id": maya_write_only.get("id"),
            "alex_control_session_id": alex_control.get("id"),
            "shared_memory_access": "none",
        },
    )


def _memory_context(metadata: dict[str, Any]) -> dict[str, Any] | None:
    context = metadata.get("memory_context")
    return context if isinstance(context, dict) else None


def _stream(
    gateway: Stage3Gateway,
    session_id: str,
    config: Stage3PrepareConfig,
    content: str,
) -> tuple[float, int, dict[str, Any]]:
    return gateway.stream_chat_diagnostics(
        session_id,
        {
            "content": content,
            "provider_id": config.provider_id,
            "model_id": config.model_id,
        },
    )


def _record(payload: dict[str, Any], record_id: str) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list):
        raise RuntimeError("memory listing did not return records")
    value = next(
        (item for item in records if isinstance(item, dict) and item.get("id") == record_id),
        None,
    )
    if value is None:
        raise RuntimeError(f"memory record is unavailable: {record_id}")
    return value


def _candidate_ids(payload: dict[str, Any]) -> list[str]:
    values = payload.get("candidates")
    if not isinstance(values, list):
        return []
    return sorted(str(item.get("id")) for item in values if isinstance(item, dict) and item.get("id"))


def _wait_for_new_candidate(
    gateway: Stage3Gateway,
    session_id: str,
    before: set[str],
    *,
    settle_seconds: float,
) -> dict[str, Any]:
    deadline = time.perf_counter() + settle_seconds
    last: dict[str, Any] | None = None
    while True:
        last = gateway.list_candidates(session_id)
        candidates = last.get("candidates")
        if isinstance(candidates, list):
            fresh = [
                item
                for item in candidates
                if isinstance(item, dict) and str(item.get("id")) not in before
            ]
            if len(fresh) == 1:
                return fresh[0]
            if len(fresh) > 1:
                raise RuntimeError("more than one new pending candidate appeared")
        if time.perf_counter() >= deadline:
            break
        time.sleep(min(0.5, max(0.0, deadline - time.perf_counter())))
    pending_count = len(_candidate_ids(last or {}))
    jobs = [
        {
            "id": job.get("id"),
            "status": job.get("status"),
            "type": job.get("type"),
        }
        for job in gateway.list_jobs(limit=50, full=True)
        if job.get("type") == "assistant.memory.suggest"
    ][:5]
    raise RuntimeError(f"pending suggestion did not appear; pending_count={pending_count}; recent_jobs={jobs}")


def _explicit_write(
    gateway: Stage3Gateway,
    config: Stage3PrepareConfig,
    session_id: str,
):
    first_token_ms, response_count, metadata = _stream(
        gateway,
        session_id,
        config,
        f"remember that {marker_memory(config.run_id, 'explicit')}",
    )
    command = metadata.get("memory_command")
    if not isinstance(command, dict) or command.get("command") != "save":
        raise RuntimeError("explicit remember command did not return save diagnostics")
    if command.get("mutated") is not True:
        raise RuntimeError("explicit remember command did not mutate memory")
    ids = [str(item) for item in command.get("memory_ids") or []]
    if len(ids) != 1:
        raise RuntimeError("explicit remember command did not report one memory id")
    record = _record(gateway.list_memory(session_id), ids[0])
    if record.get("owner_type") != "character" or record.get("owner_id") != config.maya_character_id:
        raise RuntimeError("explicit memory resolved the wrong owner")
    return (
        (ids[0], first_token_ms),
        "Explicit remember wrote one approved memory to the active character owner.",
        {
            "memory_id": ids[0],
            "first_token_ms": first_token_ms,
            "response_character_count": response_count,
            "owner_type": "character",
            "owner_id": config.maya_character_id,
        },
    )


def _write_only_control(
    gateway: Stage3Gateway,
    config: Stage3PrepareConfig,
    session_id: str,
):
    state = gateway.memory_state(session_id)
    if state.get("memory_enabled") is not False or state.get("snapshot_id") is not None:
        raise RuntimeError("write-only control started with readable memory")
    status, body = gateway.create_memory_status(
        {
            "session_id": session_id,
            "scope": "global",
            "category": "fact",
            "content": marker_memory(config.run_id, "write-only"),
            "pinned": False,
        }
    )
    if status != 200:
        raise RuntimeError(f"write-only management save failed: HTTP {status}")
    record = body
    if record.get("owner_type") != "character" or record.get("owner_id") != config.maya_character_id:
        raise RuntimeError("write-only save resolved the wrong owner")
    _, _, metadata = _stream(
        gateway,
        session_id,
        config,
        "Confirm the write-only Stage 3 control is active.",
    )
    if _memory_context(metadata) is not None:
        raise RuntimeError("write-only provider completion included readable memory context")
    return (
        str(record["id"]),
        "Write-only control saved memory while exposing no readable prompt memory.",
        {
            "memory_id": record.get("id"),
            "management_status": status,
            "read_memory": False,
            "write_memory": True,
            "memory_context_present": False,
        },
    )


def _candidate_lifecycle(
    gateway: Stage3Gateway,
    config: Stage3PrepareConfig,
    session_id: str,
    explicit_memory_id: str,
):
    before = set(_candidate_ids(gateway.list_candidates(session_id)))
    first_token_ms, _, metadata = _stream(
        gateway,
        session_id,
        config,
        f"my stage three candidate is {marker(config.run_id, 'candidate')}",
    )
    if metadata.get("memory_command"):
        raise RuntimeError("ordinary inferred-content turn was treated as an explicit command")
    candidate = _wait_for_new_candidate(
        gateway,
        session_id,
        before,
        settle_seconds=config.settle_seconds,
    )
    candidate_id = str(candidate["id"])
    if candidate.get("owner_type") != "character" or candidate.get("owner_id") != config.maya_character_id:
        raise RuntimeError("pending candidate resolved the wrong owner")
    if candidate_id in memory_record_ids(gateway.list_memory(session_id)):
        raise RuntimeError("pending candidate appeared as approved memory before approval")
    state_before = gateway.memory_state(session_id)
    if candidate_id in snapshot_item_ids(state_before, active_only=False):
        raise RuntimeError("pending candidate appeared in the active snapshot")
    approved = gateway.approve_candidate(candidate_id, session_id, pinned=False)
    approved_id = str(approved["id"])
    if approved_id in snapshot_item_ids(gateway.memory_state(session_id), active_only=False):
        raise RuntimeError("approved candidate entered an existing snapshot before refresh")
    refreshed = gateway.refresh_memory(
        session_id,
        int(state_before.get("snapshot_revision") or 0) or None,
        config.token_budget,
    )
    refreshed_ids = set(snapshot_item_ids(refreshed))
    if explicit_memory_id not in refreshed_ids or approved_id not in refreshed_ids:
        raise RuntimeError("refreshed snapshot did not include approved character memories")
    return (
        (candidate_id, approved_id, first_token_ms, refreshed),
        "Inferred content became pending, stayed prompt-ineligible, and became selectable only after approval and refresh.",
        {
            "candidate_id": candidate_id,
            "approved_memory_id": approved_id,
            "first_token_ms": first_token_ms,
            "pending_was_prompt_eligible": False,
            "approved_before_refresh_selected": False,
            "refreshed_snapshot_count": len(refreshed_ids),
        },
    )


def _rejection_lifecycle(
    gateway: Stage3Gateway,
    config: Stage3PrepareConfig,
    session_id: str,
):
    before = set(_candidate_ids(gateway.list_candidates(session_id)))
    _stream(
        gateway,
        session_id,
        config,
        f"i prefer {marker(config.run_id, 'reject')}",
    )
    candidate = _wait_for_new_candidate(
        gateway,
        session_id,
        before,
        settle_seconds=config.settle_seconds,
    )
    candidate_id = str(candidate["id"])
    gateway.reject_candidate(candidate_id, session_id, pinned=False)
    pending_after = set(_candidate_ids(gateway.list_candidates(session_id)))
    if candidate_id in pending_after:
        raise RuntimeError("rejected candidate remained pending")
    return (
        candidate_id,
        "Rejected inferred memory remained excluded from approved memory and prompts.",
        {
            "candidate_id": candidate_id,
            "pending_after_reject": False,
        },
    )


def _owner_isolation(
    gateway: Stage3Gateway,
    config: Stage3PrepareConfig,
    alex_session_id: str,
    forbidden_ids: set[str],
):
    alex_ids = set(memory_record_ids(gateway.list_memory(alex_session_id)))
    if forbidden_ids & alex_ids:
        raise RuntimeError("Maya memory appeared in Alex owner listing")
    state = gateway.memory_state(alex_session_id)
    if forbidden_ids & set(snapshot_item_ids(state, active_only=False)):
        raise RuntimeError("Maya memory appeared in Alex snapshot")
    return (
        alex_ids,
        "Other-character owner listing and snapshot exclude Maya Stage 3 records.",
        {
            "alex_visible_count": len(alex_ids),
            "cross_owner_count": 0,
        },
    )


def prepare_stage3(
    gateway: Stage3Gateway,
    config: Stage3PrepareConfig,
    *,
    checkpoint_path: str | Path,
) -> Stage3Report:
    checks: list[Stage3Check] = []
    metrics = Stage3Metrics()
    if _check(checks, "gateway.health", lambda: _health(gateway)) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    if _check(checks, "fixtures.characters", lambda: _ensure_profiles(gateway, config)) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    sessions = _check(checks, "sessions.write_policies", lambda: _create_sessions(gateway, config))
    if sessions is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    maya_rw, maya_write_only, alex_control = sessions
    session_id = str(maya_rw["id"])

    explicit = _check(
        checks,
        "writes.explicit_remember",
        lambda: _explicit_write(gateway, config, session_id),
    )
    if explicit is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    explicit_memory_id, first_token_ms = explicit
    metrics.first_token_ms = first_token_ms
    metrics.explicit_record_count = 1

    write_only_id = _check(
        checks,
        "writes.write_only_control",
        lambda: _write_only_control(gateway, config, str(maya_write_only["id"])),
    )
    if write_only_id is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)

    candidate = _check(
        checks,
        "suggestions.pending_approval",
        lambda: _candidate_lifecycle(gateway, config, session_id, explicit_memory_id),
    )
    if candidate is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    candidate_id, approved_id, _, refreshed = candidate
    metrics.pending_candidate_count = 1
    metrics.approved_record_count = 1
    metrics.snapshot_record_count = len(snapshot_item_ids(refreshed))

    rejected_id = _check(
        checks,
        "suggestions.rejection",
        lambda: _rejection_lifecycle(gateway, config, session_id),
    )
    if rejected_id is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)

    if _check(
        checks,
        "memory.owner_isolation",
        lambda: _owner_isolation(
            gateway,
            config,
            str(alex_control["id"]),
            {explicit_memory_id, write_only_id, approved_id},
        ),
    ) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)

    checks.append(
        Stage3Check(
            id="restart.persistence",
            status="review",
            summary="Restart Omnix with the same Stage 3 flags, then run verify-restart.",
            observed={"checkpoint_required": True},
        )
    )
    checkpoint = Stage3Checkpoint(
        created_at=utcnow(),
        base_url=config.base_url,
        provider_id=config.provider_id,
        model_id=config.model_id,
        run_id=config.run_id,
        maya_character_id=config.maya_character_id,
        alex_character_id=config.alex_character_id,
        maya_rw_session_id=session_id,
        maya_write_only_session_id=str(maya_write_only["id"]),
        alex_control_session_id=str(alex_control["id"]),
        maya_explicit_memory_id=explicit_memory_id,
        maya_write_only_memory_id=write_only_id,
        approved_candidate_id=candidate_id,
        approved_candidate_memory_id=approved_id,
        rejected_candidate_id=rejected_id,
        maya_segment_id=str(maya_rw["active_segment_id"]),
        maya_identity_hash=str(maya_rw["effective_identity_hash"]),
        maya_snapshot_id=str(refreshed.get("snapshot_id")),
        maya_snapshot_revision=int(refreshed.get("snapshot_revision") or 0),
        marker_hashes={
            label: marker_hash(marker(config.run_id, label))
            for label in ("explicit", "write-only", "candidate", "reject")
        },
        prepare_checks=checks,
        prepare_metrics=metrics,
    )
    target = Path(checkpoint_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    return _report(
        config,
        checks,
        metrics,
        mode="prepare",
        session_id=session_id,
        checkpoint_path=target,
    )


def _verify_restart_state(gateway: Stage3Gateway, checkpoint: Stage3Checkpoint):
    session = gateway.get_session(checkpoint.maya_rw_session_id)
    state = gateway.memory_state(checkpoint.maya_rw_session_id)
    if session.get("interaction_mode") != "character" or session.get("character_id") != checkpoint.maya_character_id:
        raise RuntimeError("Maya write pilot identity changed across restart")
    if session.get("read_memory") is not True or session.get("write_memory") is not True:
        raise RuntimeError("Maya write pilot policy changed across restart")
    if session.get("shared_memory_access") != "none":
        raise RuntimeError("shared memory became active across restart")
    if session.get("active_segment_id") != checkpoint.maya_segment_id:
        raise RuntimeError("Maya write pilot segment changed across restart")
    if session.get("effective_identity_hash") != checkpoint.maya_identity_hash:
        raise RuntimeError("Maya identity hash changed across restart")
    selected = set(snapshot_item_ids(state))
    expected = {
        checkpoint.maya_explicit_memory_id,
        checkpoint.approved_candidate_memory_id,
    }
    if None in expected or not expected <= selected:
        raise RuntimeError("approved Stage 3 memories did not survive restart snapshot")
    if checkpoint.maya_write_only_memory_id not in memory_record_ids(gateway.list_memory(checkpoint.maya_write_only_session_id)):
        raise RuntimeError("write-only Stage 3 memory did not survive restart")
    return (
        (session, state),
        "Stage 3 sessions, write policy, identity, records, and snapshot survived restart.",
        {
            "snapshot_id": state.get("snapshot_id"),
            "snapshot_revision": state.get("snapshot_revision"),
            "active_snapshot_count": len(selected),
        },
    )


def _cleanup(gateway: Stage3Gateway, checkpoint: Stage3Checkpoint, token_budget: int):
    deleted = 0
    for session_id, record_id in (
        (checkpoint.maya_rw_session_id, checkpoint.maya_explicit_memory_id),
        (checkpoint.maya_write_only_session_id, checkpoint.maya_write_only_memory_id),
        (checkpoint.maya_rw_session_id, checkpoint.approved_candidate_memory_id),
    ):
        if not record_id:
            continue
        record = _record(gateway.list_memory(session_id), record_id)
        gateway.delete_memory(record_id, session_id, int(record.get("revision") or 0))
        deleted += 1
    candidates_deleted = 0
    if checkpoint.rejected_candidate_id:
        gateway.delete_candidate(
            checkpoint.rejected_candidate_id,
            checkpoint.maya_rw_session_id,
            expected_status="rejected",
        )
        candidates_deleted += 1
    if checkpoint.approved_candidate_id:
        gateway.delete_candidate(
            checkpoint.approved_candidate_id,
            checkpoint.maya_rw_session_id,
            expected_status="accepted",
        )
        candidates_deleted += 1
    refreshed = gateway.refresh_memory(
        checkpoint.maya_rw_session_id,
        checkpoint.maya_snapshot_revision,
        token_budget,
    )
    remaining_ids = set(snapshot_item_ids(refreshed, active_only=False))
    if {
        checkpoint.maya_explicit_memory_id,
        checkpoint.maya_write_only_memory_id,
        checkpoint.approved_candidate_memory_id,
    } & remaining_ids:
        raise RuntimeError("refreshed snapshot retained Stage 3 synthetic records")
    for session_id, character_id in (
        (checkpoint.maya_rw_session_id, checkpoint.maya_character_id),
        (checkpoint.maya_write_only_session_id, checkpoint.maya_character_id),
        (checkpoint.alex_control_session_id, checkpoint.alex_character_id),
    ):
        gateway.set_interaction(
            session_id,
            {
                "interaction_mode": "character",
                "character_id": character_id,
                "read_memory": False,
                "write_memory": False,
                "shared_memory_access": "none",
                "transcript_policy": "persistent",
                "continue_topic": False,
            },
        )
        gateway.delete_session(session_id)
    return (
        refreshed,
        "Stage 3 synthetic records and temporary sessions were cleaned up.",
        {
            "fixture_records_deleted": deleted,
            "fixture_candidates_deleted": candidates_deleted,
            "fixture_sessions_deleted": 3,
            "refreshed_snapshot_revision": refreshed.get("snapshot_revision"),
        },
    )


def verify_stage3_restart(
    gateway: Stage3Gateway,
    checkpoint: Stage3Checkpoint,
    *,
    token_budget: int = 4_000,
) -> Stage3Report:
    config = Stage3PrepareConfig(
        base_url=checkpoint.base_url,
        provider_id=checkpoint.provider_id,
        model_id=checkpoint.model_id,
        maya_character_id=checkpoint.maya_character_id,
        alex_character_id=checkpoint.alex_character_id,
        run_id=checkpoint.run_id,
        token_budget=token_budget,
    )
    checks = [
        item.model_copy()
        for item in checkpoint.prepare_checks
        if item.id != "restart.persistence"
    ]
    metrics = checkpoint.prepare_metrics.model_copy()
    if _check(checks, "restart.persistence", lambda: _verify_restart_state(gateway, checkpoint)) is None:
        return _report(config, checks, metrics, mode="verify-restart", session_id=checkpoint.maya_rw_session_id)
    _check(checks, "cleanup.stage3_fixtures", lambda: _cleanup(gateway, checkpoint, token_budget))
    return _report(config, checks, metrics, mode="verify-restart", session_id=checkpoint.maya_rw_session_id)


__all__ = ["prepare_stage3", "verify_stage3_restart"]
