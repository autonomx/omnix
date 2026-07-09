"""Orchestration for the Character Mode Stage 4 shared-memory pilot."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Literal

from app.assistant_memory import default_memory_service, resolve_chat_scope

from .stage4_contracts import (
    Stage4Check,
    Stage4Checkpoint,
    Stage4Metrics,
    Stage4PrepareConfig,
    Stage4Report,
    decision,
    duration_ms,
    marker_memory,
    safe_error,
    utcnow,
)
from .stage4_http import Stage4Gateway


def _check(checks: list[Stage4Check], check_id: str, operation: Callable[[], tuple[Any, str, dict[str, Any]]]) -> Any:
    started = time.perf_counter()
    try:
        value, summary, observed = operation()
    except Exception as exc:
        checks.append(Stage4Check(id=check_id, status="fail", summary=safe_error(exc), duration_ms=duration_ms(started)))
        return None
    checks.append(Stage4Check(id=check_id, status="pass", summary=summary, duration_ms=duration_ms(started), observed=observed))
    return value


def _report(config: Stage4PrepareConfig, checks: list[Stage4Check], metrics: Stage4Metrics, *, mode: Literal["prepare", "verify-restart"], session_id: str | None, checkpoint_path: str | Path | None = None) -> Stage4Report:
    return Stage4Report(
        generated_at=utcnow(), mode=mode, decision=decision(checks), base_url=config.base_url,
        run_id=config.run_id, character_id=config.character_id, shared_session_id=session_id,
        checks=checks, metrics=metrics, checkpoint_path=str(checkpoint_path) if checkpoint_path else None,
        notes=[
            "Reports contain IDs, hashes, counts, policies, and timings only; synthetic memory text and model output are not persisted.",
            "Stage 4 cleanup runs only after restart verification proves the shared-memory policy survived restart.",
        ],
    )


def _health(gateway: Stage4Gateway):
    payload = gateway.health()
    if payload.get("ok") is not True or payload.get("status") != "ready":
        raise RuntimeError("Gateway health endpoint is not ready")
    return payload, "Gateway health endpoint is ready.", {"ready": True}


def _ensure_character(gateway: Stage4Gateway, config: Stage4PrepareConfig):
    existing = next((item for item in gateway.list_characters() if item.get("id") == config.character_id), None)
    if existing and existing.get("status") == "archived":
        raise RuntimeError("Stage 4 character is archived")
    if existing is None:
        profile = gateway.create_character({
            "id": config.character_id,
            "display_name": "Maya Stage 4",
            "description": "Synthetic Stage 4 shared-memory fixture.",
            "personality_prompt": "Be concise. Treat shared System Assistant memory as read-only background context.",
            "default_greeting": "Stage 4 shared-memory fixture ready.",
            "identity_policy": {"may_claim_to_be_human": False, "may_claim_real_world_experiences": False, "disclosure_required": True},
            "shared_memory_policy": {"access": "read_only", "allowed_categories": ["fact", "preference"]},
            "enabled": True,
        })
    else:
        profile = gateway.update_character(config.character_id, {
            "expected_version": existing["active_version"],
            "shared_memory_policy": {"access": "read_only", "allowed_categories": ["fact", "preference"]},
            "enabled": True,
        })
    return profile, "Stage 4 character has a server-owned read-only category allowlist.", {
        "character_id": config.character_id,
        "profile_version": profile.get("active_version"),
        "allowed_categories": ["fact", "preference"],
    }


def _create_sessions(gateway: Stage4Gateway, config: Stage4PrepareConfig):
    common = {"provider_id": config.provider_id, "model_id": config.model_id, "transcript_policy": "persistent"}
    setup = gateway.create_session({"title": "Stage 4 System Assistant fixture setup", "interaction_mode": "system", **common})
    shared = gateway.create_session({
        "title": "Stage 4 Maya shared read-only pilot", "interaction_mode": "character",
        "character_id": config.character_id, "read_memory": False, "write_memory": False,
        "shared_memory_access": "read_only", **common,
    })
    control = gateway.create_session({
        "title": "Stage 4 Maya shared-off control", "interaction_mode": "character",
        "character_id": config.character_id, "read_memory": False, "write_memory": False,
        "shared_memory_access": "none", **common,
    })
    if shared.get("shared_memory_access") != "read_only" or control.get("shared_memory_access") != "none":
        raise RuntimeError("Stage 4 sessions resolved the wrong shared-memory policies")
    return (setup, shared, control), "Shared read-only and shared-off control sessions are active.", {
        "system_setup_session_id": setup.get("id"), "shared_session_id": shared.get("id"),
        "control_session_id": control.get("id"), "read_memory": False, "write_memory": False,
    }


def _system_context(session: dict[str, Any]):
    return resolve_chat_scope(
        str(session["id"]), profile_id=session.get("profile_id"),
        workspace_id=session.get("workspace_id"), project_id=session.get("project_id"),
    )


def _fixture_records(config: Stage4PrepareConfig, setup: dict[str, Any], shared: dict[str, Any]):
    setup_context = _system_context(setup)
    shared_context = _system_context(shared)
    service = default_memory_service()
    definitions = {
        "allowed_fact": ("global", "fact", "normal"),
        "blocked_category": ("global", "instruction", "normal"),
        "blocked_sensitive": ("workspace", "preference", "sensitive"),
        "blocked_session": ("session", "fact", "normal"),
    }
    records = {}
    for label, (scope, category, sensitivity) in definitions.items():
        context = shared_context if label == "blocked_session" else setup_context
        content = marker_memory(config.run_id, label)
        matches = [record for record in service.list_active(context) if record.content == content]
        if len(matches) > 1:
            raise RuntimeError(f"duplicate Stage 4 fixture records exist: {label}")
        records[label] = matches[0] if matches else service.create_explicit_memory(
            context, scope=scope, category=category, content=content,
            provenance_id=f"stage4:{config.run_id}:{label}", pinned=True, sensitivity=sensitivity,
        )
    return records, "Synthetic shared-memory policy fixtures are active.", {
        "fixture_memory_ids": {label: record.id for label, record in records.items()},
        "fixture_count": len(records),
    }


def _memory_context(metadata: dict[str, Any]) -> dict[str, Any] | None:
    value = metadata.get("memory_context")
    return value if isinstance(value, dict) else None


def _stream(gateway: Stage4Gateway, config: Stage4PrepareConfig, session_id: str):
    return gateway.stream_chat_diagnostics(session_id, {
        "content": "Confirm the Stage 4 shared-memory policy is active.",
        "provider_id": config.provider_id, "model_id": config.model_id,
    })


def _verify_selection(gateway: Stage4Gateway, config: Stage4PrepareConfig, session_id: str, records: dict[str, Any]):
    first_token_ms, response_count, metadata = _stream(gateway, config, session_id)
    context = _memory_context(metadata)
    if context is None:
        raise RuntimeError("shared session returned no memory diagnostics")
    expected = {records["allowed_fact"].id}
    selected = set(context.get("shared_selected_memory_ids") or [])
    if selected != expected:
        raise RuntimeError("shared selection did not contain exactly the allowlisted normal System Assistant record")
    forbidden = {records[label].id for label in ("blocked_category", "blocked_sensitive", "blocked_session")}
    if forbidden & set(context.get("selected_memory_ids") or []):
        raise RuntimeError("a blocked System Assistant record entered the character prompt")
    excluded = context.get("shared_excluded_reason_counts") or {}
    for reason in ("category_not_allowed", "sensitivity_not_normal", "session_scope_blocked"):
        if int(excluded.get(reason) or 0) < 1:
            raise RuntimeError(f"shared diagnostics did not report {reason}")
    return first_token_ms, "Only the allowlisted normal System Assistant record entered the streamed character prompt.", {
        "first_token_ms": first_token_ms, "response_character_count": response_count,
        "shared_selected_memory_ids": sorted(selected), "shared_selected_count": len(selected),
        "shared_excluded_reason_counts": excluded,
    }


def _verify_read_only(gateway: Stage4Gateway, session_id: str, allowed_record_id: str):
    status, _ = gateway.create_memory_status({
        "session_id": session_id, "scope": "global", "category": "fact",
        "content": "Stage 4 write attempt must be rejected.", "pinned": False,
    })
    if status != 403:
        raise RuntimeError(f"character management write returned HTTP {status}, expected 403")
    try:
        gateway.update_memory(allowed_record_id, session_id, 1, "Mutation must be rejected.")
    except RuntimeError as exc:
        if "HTTP 403" not in str(exc):
            raise
    else:
        raise RuntimeError("character updated shared System Assistant memory")
    return True, "Character create and edit operations cannot mutate shared System Assistant memory.", {
        "create_status": status, "update_status": 403,
    }


def _verify_off_control(gateway: Stage4Gateway, config: Stage4PrepareConfig, session_id: str):
    _, _, metadata = _stream(gateway, config, session_id)
    if _memory_context(metadata) is not None:
        raise RuntimeError("shared-off control returned memory context")
    return True, "Shared-off control exposes no System Assistant memory context.", {"memory_context_present": False}


def _toggle_bridge(gateway: Stage4Gateway, config: Stage4PrepareConfig, session: dict[str, Any], allowed_id: str):
    original_segment = session.get("active_segment_id")
    off = gateway.set_interaction(str(session["id"]), {
        "interaction_mode": "character", "character_id": config.character_id,
        "read_memory": False, "write_memory": False, "shared_memory_access": "none",
        "transcript_policy": "persistent", "continue_topic": False,
    })
    if off.get("active_segment_id") == original_segment:
        raise RuntimeError("turning shared memory off did not create a clean segment")
    _, _, off_metadata = _stream(gateway, config, str(session["id"]))
    if _memory_context(off_metadata) is not None:
        raise RuntimeError("turning shared memory off retained shared context")
    restored = gateway.set_interaction(str(session["id"]), {
        "interaction_mode": "character", "character_id": config.character_id,
        "read_memory": False, "write_memory": False, "shared_memory_access": "read_only",
        "transcript_policy": "persistent", "continue_topic": False,
    })
    if restored.get("active_segment_id") == off.get("active_segment_id"):
        raise RuntimeError("re-enabling shared memory did not create a fresh segment")
    _, _, restored_metadata = _stream(gateway, config, str(session["id"]))
    context = _memory_context(restored_metadata) or {}
    if set(context.get("shared_selected_memory_ids") or []) != {allowed_id}:
        raise RuntimeError("re-enabled shared memory did not restore the allowlisted record")
    return restored, "Turning shared access off removed the bridge; re-enabling it created a fresh segment.", {
        "segment_switch_count": 2, "restored_segment_id": restored.get("active_segment_id"),
        "restored_identity_hash": restored.get("effective_identity_hash"),
    }


def prepare_stage4(gateway: Stage4Gateway, config: Stage4PrepareConfig, *, checkpoint_path: str | Path) -> Stage4Report:
    checks: list[Stage4Check] = []
    metrics = Stage4Metrics()
    if _check(checks, "gateway.health", lambda: _health(gateway)) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    if _check(checks, "fixtures.character_policy", lambda: _ensure_character(gateway, config)) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    sessions = _check(checks, "sessions.shared_policy", lambda: _create_sessions(gateway, config))
    if sessions is None:
        return _report(config, checks, metrics, mode="prepare", session_id=None)
    setup, shared, control = sessions
    records = _check(checks, "fixtures.system_memory", lambda: _fixture_records(config, setup, shared))
    session_id = str(shared["id"])
    if records is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    selection = _check(checks, "shared.selection", lambda: _verify_selection(gateway, config, session_id, records))
    if selection is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    metrics.first_token_ms = selection
    metrics.shared_selected_count = 1
    metrics.shared_excluded_count = 3
    if _check(checks, "shared.read_only", lambda: _verify_read_only(gateway, session_id, records["allowed_fact"].id)) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    if _check(checks, "shared.off_control", lambda: _verify_off_control(gateway, config, str(control["id"]))) is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    restored = _check(checks, "shared.segment_reset", lambda: _toggle_bridge(gateway, config, shared, records["allowed_fact"].id))
    if restored is None:
        return _report(config, checks, metrics, mode="prepare", session_id=session_id)
    metrics.segment_switch_count = 2
    checks.append(Stage4Check(id="restart.persistence", status="review", summary="Restart Omnix with the same Stage 4 flags, then run verify-restart.", observed={"checkpoint_required": True}))
    checkpoint = Stage4Checkpoint(
        created_at=utcnow(), base_url=config.base_url, provider_id=config.provider_id, model_id=config.model_id,
        run_id=config.run_id, character_id=config.character_id, shared_session_id=session_id,
        control_session_id=str(control["id"]), system_setup_session_id=str(setup["id"]),
        shared_segment_id=str(restored["active_segment_id"]), shared_identity_hash=str(restored["effective_identity_hash"]),
        fixture_memory_ids={label: record.id for label, record in records.items()},
        prepare_checks=checks, prepare_metrics=metrics,
    )
    target = Path(checkpoint_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    return _report(config, checks, metrics, mode="prepare", session_id=session_id, checkpoint_path=target)


def _verify_restart(gateway: Stage4Gateway, config: Stage4PrepareConfig, checkpoint: Stage4Checkpoint):
    session = gateway.get_session(checkpoint.shared_session_id)
    if session.get("shared_memory_access") != "read_only" or session.get("read_memory") is not False or session.get("write_memory") is not False:
        raise RuntimeError("Stage 4 shared read-only policy changed across restart")
    if session.get("active_segment_id") != checkpoint.shared_segment_id:
        raise RuntimeError("Stage 4 segment changed across restart")
    if session.get("effective_identity_hash") != checkpoint.shared_identity_hash:
        raise RuntimeError("Stage 4 identity hash changed across restart")
    first_token_ms, _, metadata = _stream(gateway, config, checkpoint.shared_session_id)
    context = _memory_context(metadata) or {}
    expected = {checkpoint.fixture_memory_ids["allowed_fact"]}
    if set(context.get("shared_selected_memory_ids") or []) != expected:
        raise RuntimeError("Stage 4 shared selection changed across restart")
    return first_token_ms, "Shared policy, identity, segment, and allowlisted selection survived restart.", {
        "first_token_ms": first_token_ms, "shared_selected_memory_ids": sorted(expected),
    }


def _cleanup(gateway: Stage4Gateway, checkpoint: Stage4Checkpoint):
    service = default_memory_service()
    setup_context = _system_context(gateway.get_session(checkpoint.system_setup_session_id))
    shared_context = _system_context(gateway.get_session(checkpoint.shared_session_id))
    deleted = 0
    for label, record_id in checkpoint.fixture_memory_ids.items():
        record = service.repository.get_record(record_id)
        if record is None:
            raise RuntimeError(f"Stage 4 fixture record is unavailable during cleanup: {record_id}")
        context = shared_context if label == "blocked_session" else setup_context
        service.forget_memory(context, record_id, expected_revision=record.revision)
        deleted += 1
    gateway.set_interaction(checkpoint.shared_session_id, {
        "interaction_mode": "character", "character_id": checkpoint.character_id,
        "read_memory": False, "write_memory": False, "shared_memory_access": "none",
        "transcript_policy": "persistent", "continue_topic": False,
    })
    for session_id in (checkpoint.shared_session_id, checkpoint.control_session_id, checkpoint.system_setup_session_id):
        gateway.delete_session(session_id)
    return True, "Stage 4 synthetic records and temporary sessions were cleaned up.", {
        "fixture_records_deleted": deleted, "fixture_sessions_deleted": 3,
    }


def verify_stage4_restart(gateway: Stage4Gateway, checkpoint: Stage4Checkpoint) -> Stage4Report:
    config = Stage4PrepareConfig(
        base_url=checkpoint.base_url, provider_id=checkpoint.provider_id, model_id=checkpoint.model_id,
        character_id=checkpoint.character_id, run_id=checkpoint.run_id,
    )
    checks = [item.model_copy() for item in checkpoint.prepare_checks if item.id != "restart.persistence"]
    metrics = checkpoint.prepare_metrics.model_copy()
    result = _check(checks, "restart.persistence", lambda: _verify_restart(gateway, config, checkpoint))
    if result is None:
        return _report(config, checks, metrics, mode="verify-restart", session_id=checkpoint.shared_session_id)
    metrics.restart_first_token_ms = result
    _check(checks, "cleanup.stage4_fixtures", lambda: _cleanup(gateway, checkpoint))
    return _report(config, checks, metrics, mode="verify-restart", session_id=checkpoint.shared_session_id)


__all__ = ["prepare_stage4", "verify_stage4_restart"]
