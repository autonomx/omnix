"""Restart verification and resumable cleanup for Character Mode Stage 2."""
from __future__ import annotations

from typing import Any

from .stage2_contracts import (
    Stage2Check,
    Stage2Checkpoint,
    Stage2PrepareConfig,
    Stage2Report,
)
from .stage2_fixtures import memory_record_ids, snapshot_item_ids
from .stage2_http import Stage2Gateway
from .stage2_runner import (
    _check,
    _report,
    _validate_read_only_guards,
    _verify_post_restart_probe,
    _verify_restart_state,
)

_KNOWN_PURGE_ASSERTION = "forget did not invalidate the active Maya snapshot item"


def _record_or_none(payload: dict[str, Any], record_id: str) -> dict[str, Any] | None:
    records = payload.get("records")
    if not isinstance(records, list):
        raise RuntimeError("memory listing did not return records")
    return next(
        (
            item
            for item in records
            if isinstance(item, dict) and item.get("id") == record_id
        ),
        None,
    )


def _delete_if_present(
    gateway: Stage2Gateway,
    *,
    session_id: str,
    record_id: str,
    listing: dict[str, Any],
) -> bool:
    record = _record_or_none(listing, record_id)
    if record is None:
        return False
    revision = int(record.get("revision") or 0)
    if revision < 1:
        raise RuntimeError(f"memory record has no valid revision: {record_id}")
    gateway.delete_memory(record_id, session_id, revision)
    return True


def cleanup_and_verify_forget(
    gateway: Stage2Gateway,
    checkpoint: Stage2Checkpoint,
    token_budget: int,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Finish cleanup whether Maya forget is new or already partially completed.

    Omnix forget semantics purge matching ``memory_snapshot_items`` rows rather than
    retaining a revoked row.  Therefore successful propagation is proven by the
    record being absent from the owner listing and absent from the active snapshot.
    """

    maya_listing = gateway.list_memory(checkpoint.maya_setup_session_id)
    alex_listing = gateway.list_memory(checkpoint.alex_setup_session_id)
    system_listing = gateway.list_memory(checkpoint.system_setup_session_id)

    maya_deleted_now = _delete_if_present(
        gateway,
        session_id=checkpoint.maya_setup_session_id,
        record_id=checkpoint.maya_memory_id,
        listing=maya_listing,
    )
    alex_record = _record_or_none(alex_listing, checkpoint.alex_memory_id)
    system_record = _record_or_none(system_listing, checkpoint.system_memory_id)
    if alex_record is None:
        raise RuntimeError("Alex synthetic memory is unavailable before cleanup")
    if system_record is None:
        raise RuntimeError("System Assistant synthetic memory is unavailable before cleanup")

    maya_after = gateway.list_memory(checkpoint.maya_setup_session_id)
    if checkpoint.maya_memory_id in memory_record_ids(maya_after):
        raise RuntimeError("forgotten Maya record remains active in the owner listing")

    projected = gateway.memory_state(checkpoint.maya_pilot_session_id)
    active_ids = set(snapshot_item_ids(projected))
    all_projected_ids = set(snapshot_item_ids(projected, active_only=False))
    if checkpoint.maya_memory_id in active_ids:
        raise RuntimeError("forgotten Maya record remains active in the pilot snapshot")
    if {checkpoint.alex_memory_id, checkpoint.system_memory_id} & active_ids:
        raise RuntimeError("cross-owner memory appeared in the Maya pilot snapshot")

    if checkpoint.alex_memory_id not in memory_record_ids(
        gateway.list_memory(checkpoint.alex_setup_session_id)
    ):
        raise RuntimeError("Maya forget removed Alex memory")
    if checkpoint.system_memory_id not in memory_record_ids(
        gateway.list_memory(checkpoint.system_setup_session_id)
    ):
        raise RuntimeError("Maya forget removed System Assistant memory")

    revision = int(projected.get("snapshot_revision") or 0)
    if revision < 1:
        raise RuntimeError("Maya pilot snapshot has no valid revision after forget")
    refreshed = gateway.refresh_memory(
        checkpoint.maya_pilot_session_id,
        revision,
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

    projection_mode = (
        "revoked_item"
        if checkpoint.maya_memory_id in all_projected_ids
        else "purged_item"
    )
    return (
        refreshed,
        "Maya forget propagated safely; synthetic fixtures were cleaned up.",
        {
            "maya_deleted_during_this_run": maya_deleted_now,
            "maya_projection_mode": projection_mode,
            "maya_active_after_forget": False,
            "refreshed_snapshot_revision": refreshed.get("snapshot_revision"),
            "alex_preserved_during_maya_forget": True,
            "system_preserved_during_maya_forget": True,
            "fixture_sessions_deleted": 4,
            "fixture_records_deleted_or_previously_deleted": 3,
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
    if _check(
        checks,
        "restart.persistence",
        lambda: _verify_restart_state(gateway, checkpoint),
    ) is None:
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
        lambda: cleanup_and_verify_forget(gateway, checkpoint, token_budget),
    )
    return _report(
        config,
        checks,
        metrics,
        mode="verify-restart",
        session_id=checkpoint.maya_pilot_session_id,
    )


def _validate_recovery_evidence(
    checkpoint: Stage2Checkpoint,
    failed_report: Stage2Report,
) -> tuple[bool, str, dict[str, Any]]:
    if failed_report.mode != "verify-restart" or failed_report.decision != "blocked":
        raise RuntimeError("recovery requires a blocked verify-restart report")
    if (
        failed_report.run_id != checkpoint.run_id
        or failed_report.maya_character_id != checkpoint.maya_character_id
        or failed_report.maya_pilot_session_id != checkpoint.maya_pilot_session_id
    ):
        raise RuntimeError("failed report does not match the Stage 2 checkpoint")
    statuses = {item.id: item for item in failed_report.checks}
    for check_id in (
        "restart.persistence",
        "restart.prompt_selection",
        "restart.read_only_guards",
    ):
        if statuses.get(check_id) is None or statuses[check_id].status != "pass":
            raise RuntimeError(f"required prior check did not pass: {check_id}")
    cleanup = statuses.get("cleanup.forget_isolation")
    if cleanup is None or cleanup.status != "fail":
        raise RuntimeError("failed report does not contain the expected cleanup failure")
    if cleanup.summary != _KNOWN_PURGE_ASSERTION:
        raise RuntimeError("cleanup failure is not the known snapshot-purge assertion")
    return (
        True,
        "Prior restart, prompt-selection, and read-only checks passed; recovery is eligible.",
        {
            "prior_decision": failed_report.decision,
            "prior_cleanup_summary": cleanup.summary,
            "matched_checkpoint": True,
        },
    )


def resume_stage2_cleanup(
    gateway: Stage2Gateway,
    checkpoint: Stage2Checkpoint,
    failed_report: Stage2Report,
    *,
    token_budget: int = 4_000,
) -> Stage2Report:
    config = Stage2PrepareConfig(
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
        for item in failed_report.checks
        if item.id != "cleanup.forget_isolation"
    ]
    metrics = failed_report.metrics.model_copy()
    evidence = _check(
        checks,
        "recovery.prior_evidence",
        lambda: _validate_recovery_evidence(checkpoint, failed_report),
    )
    if evidence is None:
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
        lambda: cleanup_and_verify_forget(gateway, checkpoint, token_budget),
    )
    report = _report(
        config,
        checks,
        metrics,
        mode="verify-restart",
        session_id=checkpoint.maya_pilot_session_id,
    )
    report.notes.append(
        "Cleanup resumed from a prior blocked run after the server had already purged the Maya record and snapshot item."
    )
    return report


__all__ = [
    "cleanup_and_verify_forget",
    "resume_stage2_cleanup",
    "verify_stage2_restart",
]
