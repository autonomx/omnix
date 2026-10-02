"""Orchestration for the Character Mode Stage 2 read-only memory pilot."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .stage2_contracts import (
    Stage2Check,
    Stage2Checkpoint,
    Stage2Metrics,
    Stage2PrepareConfig,
    Stage2Report,
    decision,
    duration_ms,
    marker,
    marker_hash,
    safe_error,
    utcnow,
)
from .stage2_fixtures import (
    create_character_session,
    create_system_setup_session,
    ensure_character,
    ensure_synthetic_memory,
    memory_candidate_ids,
    memory_record_ids,
    snapshot_item_ids,
)
from .stage2_http import Stage2Gateway


def _check(
    checks: list[Stage2Check],
    check_id: str,
    operation: Callable[[], tuple[Any, str, dict[str, Any]]],
) -> Any:
    started = time.perf_counter()
    try:
        value, summary, observed = operation()
    except Exception as exc:
        checks.append(
            Stage2Check(
                id=check_id,
                status="fail",
                summary=safe_error(exc),
                duration_ms=duration_ms(started),
            )
        )
        return None
    checks.append(
        Stage2Check(
            id=check_id,
            status="pass",
            summary=summary,
            duration_ms=duration_ms(started),
            observed=observed,
        )
    )
    return value


def _health(gateway: Stage2Gateway):
    payload = gateway.health()
    if payload.get("ok") is not True or payload.get("status") != "ready":
        raise RuntimeError("Gateway health endpoint is not ready")
    return payload, "Gateway health endpoint is ready.", {"ready": True}


def _ensure_profiles(gateway: Stage2Gateway, config: Stage2PrepareConfig):
    maya = ensure_character(gateway, config.maya_character_id, "Maya Stage 2")
    alex = ensure_character(gateway, config.alex_character_id, "Alex Stage 2")
    return (
        (maya, alex),
        "Synthetic Maya and Alex isolation profiles are active.",
        {
            "maya_character_id": config.maya_character_id,
            "alex_character_id": config.alex_character_id,
            "maya_profile_version": maya.get("active_version"),
            "alex_profile_version": alex.get("active_version"),
        },
    )


def _create_fixtures(gateway: Stage2Gateway, config: Stage2PrepareConfig):
    maya_setup = create_character_session(
        gateway,
        config,
        character_id=config.maya_character_id,
        title="Stage 2 Maya controlled memory setup",
        read_memory=False,
        write_memory=True,
    )
    alex_setup = create_character_session(
        gateway,
        config,
        character_id=config.alex_character_id,
        title="Stage 2 Alex controlled memory setup",
        read_memory=False,
        write_memory=True,
    )
    system_setup = create_system_setup_session(gateway, config)
    maya_memory = ensure_synthetic_memory(
        gateway,
        session_id=str(maya_setup["id"]),
        run_id=config.run_id,
        owner_label="maya",
    )
    alex_memory = ensure_synthetic_memory(
        gateway,
        session_id=str(alex_setup["id"]),
        run_id=config.run_id,
        owner_label="alex",
    )
    system_memory = ensure_synthetic_memory(
        gateway,
        session_id=str(system_setup["id"]),
        run_id=config.run_id,
        owner_label="system",
    )
    for expected_owner, record in (
        (config.maya_character_id, maya_memory),
        (config.alex_character_id, alex_memory),
        ("system-assistant", system_memory),
    ):
        if record.get("owner_id") != expected_owner:
            raise RuntimeError(f"synthetic memory resolved the wrong owner: {expected_owner}")
        if record.get("trust_level") != "user_approved" or record.get("status") != "active":
            raise RuntimeError("synthetic memory is not an active approved record")
        if record.get("pinned") is not True:
            raise RuntimeError("synthetic Stage 2 memory must be pinned")
    return (
        (maya_setup, alex_setup, system_setup, maya_memory, alex_memory, system_memory),
        "Pinned synthetic records were created through controlled owner-specific setup sessions.",
        {
            "maya_memory_id": maya_memory.get("id"),
            "alex_memory_id": alex_memory.get("id"),
            "system_memory_id": system_memory.get("id"),
            "marker_hashes": {
                owner: marker_hash(marker(config.run_id, owner))
                for owner in ("maya", "alex", "system")
            },
        },
    )


def _create_pilots(gateway: Stage2Gateway, config: Stage2PrepareConfig):
    maya = create_character_session(
        gateway,
        config,
        character_id=config.maya_character_id,
        title="Stage 2 Maya read-only memory pilot",
        read_memory=True,
        write_memory=False,
    )
    alex = create_character_session(
        gateway,
        config,
        character_id=config.alex_character_id,
        title="Stage 2 Alex read-only isolation control",
        read_memory=True,
        write_memory=False,
    )
    for expected_owner, session in (
        (config.maya_character_id, maya),
        (config.alex_character_id, alex),
    ):
        if session.get("interaction_mode") != "character":
            raise RuntimeError("pilot session did not enter Character Mode")
        if session.get("character_id") != expected_owner:
            raise RuntimeError("pilot session resolved the wrong character")
        if session.get("read_memory") is not True or session.get("write_memory") is not False:
            raise RuntimeError("pilot session is not read-only")
        if session.get("shared_memory_access") != "none":
            raise RuntimeError("pilot session enabled shared System Assistant memory")
        if not session.get("memory_snapshot_id"):
            raise RuntimeError("read-only pilot session did not receive a memory snapshot")
    return (
        (maya, alex),
        "Maya and Alex pilot sessions are read-only with shared memory disabled.",
        {
            "maya_session_id": maya.get("id"),
            "alex_session_id": alex.get("id"),
            "maya_snapshot_id": maya.get("memory_snapshot_id"),
            "alex_snapshot_id": alex.get("memory_snapshot_id"),
        },
    )


def _validate_owner_isolation(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    maya_session: dict[str, Any],
    alex_session: dict[str, Any],
    system_setup: dict[str, Any],
    maya_memory: dict[str, Any],
    alex_memory: dict[str, Any],
    system_memory: dict[str, Any],
):
    maya_ids = set(memory_record_ids(gateway.list_memory(str(maya_session["id"]))))
    alex_ids = set(memory_record_ids(gateway.list_memory(str(alex_session["id"]))))
    system_ids = set(memory_record_ids(gateway.list_memory(str(system_setup["id"]))))
    target_ids = {
        "maya": str(maya_memory["id"]),
        "alex": str(alex_memory["id"]),
        "system": str(system_memory["id"]),
    }
    if target_ids["maya"] not in maya_ids or {target_ids["alex"], target_ids["system"]} & maya_ids:
        raise RuntimeError("Maya memory listing crossed an owner boundary")
    if target_ids["alex"] not in alex_ids or {target_ids["maya"], target_ids["system"]} & alex_ids:
        raise RuntimeError("Alex memory listing crossed an owner boundary")
    if target_ids["system"] not in system_ids or {target_ids["maya"], target_ids["alex"]} & system_ids:
        raise RuntimeError("System Assistant memory listing crossed an owner boundary")

    maya_state = gateway.memory_state(str(maya_session["id"]))
    alex_state = gateway.memory_state(str(alex_session["id"]))
    maya_snapshot_ids = set(snapshot_item_ids(maya_state))
    alex_snapshot_ids = set(snapshot_item_ids(alex_state))
    if maya_state.get("owner_type") != "character" or maya_state.get("owner_id") != config.maya_character_id:
        raise RuntimeError("Maya snapshot resolved the wrong owner")
    if alex_state.get("owner_type") != "character" or alex_state.get("owner_id") != config.alex_character_id:
        raise RuntimeError("Alex snapshot resolved the wrong owner")
    if target_ids["maya"] not in maya_snapshot_ids or {target_ids["alex"], target_ids["system"]} & maya_snapshot_ids:
        raise RuntimeError("Maya snapshot crossed an owner boundary")
    if target_ids["alex"] not in alex_snapshot_ids or {target_ids["maya"], target_ids["system"]} & alex_snapshot_ids:
        raise RuntimeError("Alex snapshot crossed an owner boundary")
    return (
        (maya_state, alex_state),
        "Owner filtering excludes System Assistant and other-character records before snapshot use.",
        {
            "maya_visible_count": len(maya_ids),
            "alex_visible_count": len(alex_ids),
            "system_visible_count": len(system_ids),
            "maya_snapshot_count": len(maya_snapshot_ids),
            "alex_snapshot_count": len(alex_snapshot_ids),
            "cross_owner_target_count": 0,
        },
    )


def _memory_context(metadata: dict[str, Any]) -> dict[str, Any]:
    context = metadata.get("memory_context")
    if not isinstance(context, dict):
        raise RuntimeError("provider completion did not include memory diagnostics")
    return context


def _run_prompt_probe(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    session_id: str,
    maya_memory_id: str,
    forbidden_ids: set[str],
):
    first_token_ms, response_count, metadata = gateway.stream_chat_diagnostics(
        session_id,
        {
            "content": f"My stage two pilot preference is {marker(config.run_id, 'probe-write-attempt')}.",
            "provider_id": config.provider_id,
            "model_id": config.model_id,
        },
    )
    context = _memory_context(metadata)
    selected = set(str(value) for value in context.get("selected_memory_ids") or [])
    if context.get("status") != "resolved":
        raise RuntimeError(f"memory diagnostics were not resolved: {context.get('status')}")
    if context.get("owner_type") != "character" or context.get("owner_id") != config.maya_character_id:
        raise RuntimeError("provider memory diagnostics resolved the wrong owner")
    if maya_memory_id not in selected:
        raise RuntimeError("Maya synthetic memory was not selected for the provider prompt")
    if selected & forbidden_ids:
        raise RuntimeError("provider prompt selected cross-owner memory")
    return (
        (first_token_ms, selected),
        "Provider generation selected Maya-owned memory and excluded other owners.",
        {
            "first_token_ms": first_token_ms,
            "response_character_count": response_count,
            "selected_memory_count": len(selected),
            "owner_type": context.get("owner_type"),
            "owner_id": context.get("owner_id"),
            "forbidden_selected_count": 0,
        },
    )


def _validate_read_only_guards(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    session_id: str,
    baseline_record_ids: list[str],
    baseline_candidate_ids: list[str],
):
    _, _, metadata = gateway.stream_chat_diagnostics(
        session_id,
        {
            "content": f"remember that {marker(config.run_id, 'explicit-write-attempt')}",
            "provider_id": config.provider_id,
            "model_id": config.model_id,
        },
    )
    command = metadata.get("memory_command")
    if not isinstance(command, dict) or command.get("command") != "save":
        raise RuntimeError("explicit memory command did not return command diagnostics")
    if command.get("mutated") is not False or command.get("memory_ids"):
        raise RuntimeError("read-only explicit memory command mutated memory")

    status, body = gateway.create_memory_status(
        {
            "session_id": session_id,
            "scope": "global",
            "category": "fact",
            "content": f"Synthetic forbidden write: {marker(config.run_id, 'api-write-attempt')}",
            "pinned": False,
        }
    )
    detail = body.get("detail") if isinstance(body.get("detail"), dict) else {}
    if status != 403 or detail.get("message") != "character_memory_write_disabled":
        raise RuntimeError(f"read-only management write was not rejected: HTTP {status}")

    if config.settle_seconds:
        time.sleep(config.settle_seconds)
    after_records = memory_record_ids(gateway.list_memory(session_id))
    after_candidates = memory_candidate_ids(gateway.list_candidates(session_id))
    if after_records != baseline_record_ids:
        raise RuntimeError("read-only pilot created or removed approved memory")
    if after_candidates != baseline_candidate_ids:
        raise RuntimeError("read-only pilot created or resolved pending suggestions")
    return (
        (after_records, after_candidates),
        "Explicit commands, management APIs, and background extraction produced no writes.",
        {
            "management_status": status,
            "record_count_before": len(baseline_record_ids),
            "record_count_after": len(after_records),
            "candidate_count_before": len(baseline_candidate_ids),
            "candidate_count_after": len(after_candidates),
            "explicit_command_mutated": False,
        },
    )


def _validate_memory_toggle(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    session: dict[str, Any],
    maya_memory_id: str,
):
    session_id = str(session["id"])
    initial_segment = session.get("active_segment_id")
    initial_snapshot = session.get("memory_snapshot_id")
    disabled = gateway.set_interaction(
        session_id,
        {
            "interaction_mode": "character",
            "character_id": config.maya_character_id,
            "read_memory": False,
            "write_memory": False,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
            "continue_topic": False,
        },
    )
    if disabled.get("active_segment_id") == initial_segment:
        raise RuntimeError("memory policy change did not create a new segment")
    if disabled.get("memory_snapshot_id") is not None or int(disabled.get("memory_record_count") or 0):
        raise RuntimeError("memory-off transition retained an active snapshot")
    _, _, metadata = gateway.stream_chat_diagnostics(
        session_id,
        {
            "content": "Confirm that this memory-off control turn is active.",
            "provider_id": config.provider_id,
            "model_id": config.model_id,
        },
    )
    if "memory_context" in metadata:
        raise RuntimeError("memory-off provider completion retained memory context")

    enabled = gateway.set_interaction(
        session_id,
        {
            "interaction_mode": "character",
            "character_id": config.maya_character_id,
            "read_memory": True,
            "write_memory": False,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
            "continue_topic": False,
        },
    )
    if enabled.get("active_segment_id") in {initial_segment, disabled.get("active_segment_id")}:
        raise RuntimeError("memory re-enable did not create a fresh segment")
    if not enabled.get("memory_snapshot_id") or enabled.get("memory_snapshot_id") == initial_snapshot:
        raise RuntimeError("memory re-enable did not create a fresh snapshot")
    state = gateway.memory_state(session_id)
    if maya_memory_id not in snapshot_item_ids(state):
        raise RuntimeError("fresh read-only snapshot does not contain Maya memory")
    return (
        (enabled, state),
        "Memory-off and read-only transitions create clean segments and fresh snapshots.",
        {
            "initial_segment_id": initial_segment,
            "memory_off_segment_id": disabled.get("active_segment_id"),
            "read_only_segment_id": enabled.get("active_segment_id"),
            "initial_snapshot_id": initial_snapshot,
            "read_only_snapshot_id": enabled.get("memory_snapshot_id"),
            "context_switch_count": 2,
        },
    )


def _report(
    config: Stage2PrepareConfig,
    checks: list[Stage2Check],
    metrics: Stage2Metrics,
    *,
    mode: str,
    session_id: str | None,
    checkpoint_path: str | Path | None = None,
) -> Stage2Report:
    return Stage2Report(
        generated_at=utcnow(),
        mode=mode,  # type: ignore[arg-type]
        decision=decision(checks),
        base_url=config.base_url,
        run_id=config.run_id,
        maya_character_id=config.maya_character_id,
        maya_pilot_session_id=session_id,
        checks=checks,
        metrics=metrics,
        checkpoint_path=str(checkpoint_path) if checkpoint_path else None,
        notes=[
            "Reports contain IDs, hashes, counts, policies, and timings only; synthetic memory text and model output are not persisted.",
            "Character setup sessions are controlled fixtures and are removed after successful restart verification.",
        ],
    )


def prepare_stage2(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    *,
    checkpoint_path: str | Path,
) -> Stage2Report:
    checks: list[Stage2Check] = []
    metrics = Stage2Metrics()
    if _check(checks, "gateway.health", lambda: _health(gateway)) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    if _check(checks, "fixtures.characters", lambda: _ensure_profiles(gateway, config)) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    fixtures = _check(checks, "fixtures.memory", lambda: _create_fixtures(gateway, config))
    if fixtures is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    maya_setup, alex_setup, system_setup, maya_memory, alex_memory, system_memory = fixtures
    pilots = _check(checks, "sessions.read_only", lambda: _create_pilots(gateway, config))
    if pilots is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    maya_pilot, alex_pilot = pilots
    session_id = str(maya_pilot["id"])

    isolated = _check(
        checks,
        "memory.owner_isolation",
        lambda: _validate_owner_isolation(
            gateway,
            config,
            maya_pilot,
            alex_pilot,
            system_setup,
            maya_memory,
            alex_memory,
            system_memory,
        ),
    )
    if isolated is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    maya_state, _ = isolated
    metrics.snapshot_record_count = len(snapshot_item_ids(maya_state))

    baseline_records = memory_record_ids(gateway.list_memory(session_id))
    baseline_candidates = memory_candidate_ids(gateway.list_candidates(session_id))
    probe = _check(
        checks,
        "prompt.read_only_selection",
        lambda: _run_prompt_probe(
            gateway,
            config,
            session_id,
            str(maya_memory["id"]),
            {str(alex_memory["id"]), str(system_memory["id"])},
        ),
    )
    if probe is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    metrics.first_token_ms = probe[0]
    metrics.selected_memory_count = len(probe[1])

    if _check(
        checks,
        "writes.read_only_guards",
        lambda: _validate_read_only_guards(
            gateway,
            config,
            session_id,
            baseline_records,
            baseline_candidates,
        ),
    ) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)

    toggled = _check(
        checks,
        "memory.policy_switch",
        lambda: _validate_memory_toggle(
            gateway,
            config,
            maya_pilot,
            str(maya_memory["id"]),
        ),
    )
    if toggled is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    final_session, final_state = toggled
    metrics.context_switch_count = 2
    metrics.snapshot_record_count = len(snapshot_item_ids(final_state))

    checks.append(
        Stage2Check(
            id="restart.persistence",
            status="review",
            summary="Restart Omnix with the same Stage 2 flags, then run verify-restart.",
            observed={"checkpoint_required": True},
        )
    )
    checkpoint = Stage2Checkpoint(
        created_at=utcnow(),
        base_url=config.base_url,
        provider_id=config.provider_id,
        model_id=config.model_id,
        run_id=config.run_id,
        maya_character_id=config.maya_character_id,
        alex_character_id=config.alex_character_id,
        maya_setup_session_id=str(maya_setup["id"]),
        alex_setup_session_id=str(alex_setup["id"]),
        system_setup_session_id=str(system_setup["id"]),
        maya_pilot_session_id=session_id,
        alex_pilot_session_id=str(alex_pilot["id"]),
        maya_segment_id=str(final_session["active_segment_id"]),
        maya_identity_hash=str(final_session["effective_identity_hash"]),
        maya_snapshot_id=str(final_state["snapshot_id"]),
        maya_snapshot_revision=int(final_state["snapshot_revision"]),
        maya_memory_id=str(maya_memory["id"]),
        alex_memory_id=str(alex_memory["id"]),
        system_memory_id=str(system_memory["id"]),
        baseline_maya_record_ids=baseline_records,
        baseline_maya_candidate_ids=baseline_candidates,
        marker_hashes={
            owner: marker_hash(marker(config.run_id, owner))
            for owner in ("maya", "alex", "system")
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


def _verify_restart_state(gateway: Stage2Gateway, checkpoint: Stage2Checkpoint):
    session = gateway.get_session(checkpoint.maya_pilot_session_id)
    state = gateway.memory_state(checkpoint.maya_pilot_session_id)
    if session.get("interaction_mode") != "character" or session.get("character_id") != checkpoint.maya_character_id:
        raise RuntimeError("Maya pilot identity changed across restart")
    if session.get("read_memory") is not True or session.get("write_memory") is not False:
        raise RuntimeError("Maya pilot read-only policy changed across restart")
    if session.get("shared_memory_access") != "none":
        raise RuntimeError("shared memory became active across restart")
    if session.get("active_segment_id") != checkpoint.maya_segment_id:
        raise RuntimeError("Maya pilot segment changed across restart")
    if session.get("effective_identity_hash") != checkpoint.maya_identity_hash:
        raise RuntimeError("Maya identity hash changed across restart")
    if state.get("snapshot_id") != checkpoint.maya_snapshot_id:
        raise RuntimeError("Maya snapshot ID changed across restart")
    if int(state.get("snapshot_revision") or 0) != checkpoint.maya_snapshot_revision:
        raise RuntimeError("Maya snapshot revision changed across restart")
    selected = set(snapshot_item_ids(state))
    if checkpoint.maya_memory_id not in selected:
        raise RuntimeError("Maya synthetic memory disappeared across restart")
    if {checkpoint.alex_memory_id, checkpoint.system_memory_id} & selected:
        raise RuntimeError("cross-owner memory appeared after restart")
    return (
        (session, state),
        "Read-only policy, owner, segment, identity hash, and snapshot survived restart.",
        {
            "segment_id": checkpoint.maya_segment_id,
            "snapshot_id": checkpoint.maya_snapshot_id,
            "snapshot_revision": checkpoint.maya_snapshot_revision,
            "active_snapshot_count": len(selected),
            "cross_owner_target_count": 0,
        },
    )


def _verify_post_restart_probe(gateway: Stage2Gateway, checkpoint: Stage2Checkpoint):
    config = Stage2PrepareConfig(
        base_url=checkpoint.base_url,
        provider_id=checkpoint.provider_id,
        model_id=checkpoint.model_id,
        maya_character_id=checkpoint.maya_character_id,
        alex_character_id=checkpoint.alex_character_id,
        run_id=checkpoint.run_id,
    )
    probe = _run_prompt_probe(
        gateway,
        config,
        checkpoint.maya_pilot_session_id,
        checkpoint.maya_memory_id,
        {checkpoint.alex_memory_id, checkpoint.system_memory_id},
    )
    return probe


def _cleanup_and_verify_forget(
    gateway: Stage2Gateway,
    checkpoint: Stage2Checkpoint,
    token_budget: int,
):
    maya_listing = gateway.list_memory(checkpoint.maya_setup_session_id)
    alex_listing = gateway.list_memory(checkpoint.alex_setup_session_id)
    system_listing = gateway.list_memory(checkpoint.system_setup_session_id)
    maya_record = _record(maya_listing, checkpoint.maya_memory_id)
    alex_record = _record(alex_listing, checkpoint.alex_memory_id)
    system_record = _record(system_listing, checkpoint.system_memory_id)

    gateway.delete_memory(
        checkpoint.maya_memory_id,
        checkpoint.maya_setup_session_id,
        int(maya_record.get("revision") or 0),
    )
    invalidated = gateway.memory_state(checkpoint.maya_pilot_session_id)
    inactive_ids = set(snapshot_item_ids(invalidated, active_only=False))
    active_ids = set(snapshot_item_ids(invalidated))
    if checkpoint.maya_memory_id not in inactive_ids or checkpoint.maya_memory_id in active_ids:
        raise RuntimeError("forget did not invalidate the active Maya snapshot item")
    if checkpoint.alex_memory_id not in memory_record_ids(
        gateway.list_memory(checkpoint.alex_setup_session_id)
    ):
        raise RuntimeError("Maya forget removed Alex memory")
    if checkpoint.system_memory_id not in memory_record_ids(
        gateway.list_memory(checkpoint.system_setup_session_id)
    ):
        raise RuntimeError("Maya forget removed System Assistant memory")

    refreshed = gateway.refresh_memory(
        checkpoint.maya_pilot_session_id,
        int(invalidated.get("snapshot_revision") or 0),
        token_budget,
    )
    if checkpoint.maya_memory_id in snapshot_item_ids(refreshed, active_only=False):
        raise RuntimeError("refreshed Maya snapshot retained the forgotten record")

    gateway.delete_memory(
        checkpoint.alex_memory_id,
        checkpoint.alex_setup_session_id,
        int(alex_record.get("revision") or 0),
    )
    gateway.delete_memory(
        checkpoint.system_memory_id,
        checkpoint.system_setup_session_id,
        int(system_record.get("revision") or 0),
    )
    for session_id, character_id in (
        (checkpoint.maya_setup_session_id, checkpoint.maya_character_id),
        (checkpoint.alex_setup_session_id, checkpoint.alex_character_id),
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
    for session_id in (
        checkpoint.maya_setup_session_id,
        checkpoint.alex_setup_session_id,
        checkpoint.system_setup_session_id,
        checkpoint.alex_pilot_session_id,
    ):
        gateway.delete_session(session_id)
    return (
        refreshed,
        "Forgetting Maya invalidated only Maya snapshots; synthetic fixtures were cleaned up.",
        {
            "maya_invalidated_count": int(invalidated.get("snapshot", {}).get("invalidated_count") or 0),
            "refreshed_snapshot_revision": refreshed.get("snapshot_revision"),
            "alex_preserved_during_maya_forget": True,
            "system_preserved_during_maya_forget": True,
            "fixture_sessions_deleted": 4,
            "fixture_records_deleted": 3,
        },
    )


def verify_stage2_restart(
    gateway: Stage2Gateway,
    checkpoint: Stage2Checkpoint,
    *,
    settle_seconds: float = 4,
    token_budget: int = 4_000,
) -> Stage2Report:
    config = Stage2PrepareConfig(
        base_url=checkpoint.base_url,
        provider_id=checkpoint.provider_id,
        model_id=checkpoint.model_id,
        maya_character_id=checkpoint.maya_character_id,
        alex_character_id=checkpoint.alex_character_id,
        run_id=checkpoint.run_id,
        settle_seconds=settle_seconds,
        token_budget=token_budget,
    )
    checks = [
        item.model_copy()
        for item in checkpoint.prepare_checks
        if item.id != "restart.persistence"
    ]
    metrics = checkpoint.prepare_metrics.model_copy()
    if _check(checks, "restart.persistence", lambda: _verify_restart_state(gateway, checkpoint)) is None:
        return _report(
            config,
            checks,
            metrics,
            mode="verify-restart",
            session_id=checkpoint.maya_pilot_session_id,
        )
    probe = _check(
        checks,
        "restart.prompt_selection",
        lambda: _verify_post_restart_probe(gateway, checkpoint),
    )
    if probe is None:
        return _report(
            config,
            checks,
            metrics,
            mode="verify-restart",
            session_id=checkpoint.maya_pilot_session_id,
        )
    metrics.restart_first_token_ms = probe[0]

    if _check(
        checks,
        "restart.read_only_guards",
        lambda: _validate_read_only_guards(
            gateway,
            config,
            checkpoint.maya_pilot_session_id,
            checkpoint.baseline_maya_record_ids,
            checkpoint.baseline_maya_candidate_ids,
        ),
    ) is None:
        return _report(
            config,
            checks,
            metrics,
            mode="verify-restart",
            session_id=checkpoint.maya_pilot_session_id,
        )

    _check(
        checks,
        "cleanup.forget_isolation",
        lambda: _cleanup_and_verify_forget(gateway, checkpoint, token_budget),
    )
    return _report(
        config,
        checks,
        metrics,
        mode="verify-restart",
        session_id=checkpoint.maya_pilot_session_id,
    )


__all__ = ["prepare_stage2", "verify_stage2_restart"]
