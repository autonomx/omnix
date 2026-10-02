"""Artifact-free live-state discovery for Character Mode Stage 2 cleanup."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .stage2_contracts import (
    Stage2Check,
    Stage2Checkpoint,
    Stage2Metrics,
    Stage2PrepareConfig,
    Stage2Report,
    decision,
    marker,
    marker_hash,
    marker_memory,
    utcnow,
)
from .stage2_fixtures import memory_candidate_ids, memory_record_ids, snapshot_item_ids
from .stage2_http import Stage2Gateway
from .stage2_verification import cleanup_and_verify_forget

MAYA_SETUP_TITLE = "Stage 2 Maya controlled memory setup"
ALEX_SETUP_TITLE = "Stage 2 Alex controlled memory setup"
SYSTEM_SETUP_TITLE = "Stage 2 System Assistant memory fixture"
ALEX_CONTROL_TITLE = "Stage 2 Alex read-only isolation control"
MAYA_PILOT_TITLE = "Stage 2 Maya read-only memory pilot"

TEMPORARY_TITLES = (
    MAYA_SETUP_TITLE,
    ALEX_SETUP_TITLE,
    SYSTEM_SETUP_TITLE,
    ALEX_CONTROL_TITLE,
)


@dataclass(frozen=True)
class _FixtureRecord:
    id: str
    revision: int
    owner_type: str
    owner_id: str


def _blocked(
    config: Stage2PrepareConfig,
    check_id: str,
    summary: str,
    observed: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> Stage2Report:
    return Stage2Report(
        generated_at=utcnow(),
        mode="discover-cleanup",
        decision="blocked",
        base_url=config.base_url,
        run_id=config.run_id,
        maya_character_id=config.maya_character_id,
        maya_pilot_session_id=session_id,
        checks=[
            Stage2Check(
                id=check_id,
                status="fail",
                summary=summary,
                observed=observed or {},
            )
        ],
        metrics=Stage2Metrics(),
        notes=[
            "Discovery cleanup reports contain IDs, hashes, counts, policies, and action statuses only.",
            "Synthetic memory text and model output are not persisted.",
        ],
    )


def _report(
    config: Stage2PrepareConfig,
    checks: list[Stage2Check],
    observed: dict[str, Any],
    *,
    session_id: str | None,
) -> Stage2Report:
    notes = [
        "Discovery cleanup reports contain IDs, hashes, counts, policies, and action statuses only.",
        "Synthetic memory text and model output are not persisted.",
    ]
    if observed.get("dry_run"):
        notes.append("Dry-run only: no mutation was attempted.")
    return Stage2Report(
        generated_at=utcnow(),
        mode="discover-cleanup",
        decision=decision(checks),
        base_url=config.base_url,
        run_id=config.run_id,
        maya_character_id=config.maya_character_id,
        maya_pilot_session_id=session_id,
        checks=checks,
        metrics=Stage2Metrics(
            snapshot_record_count=int(observed.get("maya_snapshot_active_count") or 0)
        ),
        notes=notes,
    )


def _sessions(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        values = payload.get("sessions")
    else:
        values = payload
    if not isinstance(values, list):
        raise RuntimeError("session listing did not return sessions")
    return [item for item in values if isinstance(item, dict)]


def _unique_by_title(
    gateway: Stage2Gateway,
    listing: list[dict[str, Any]],
    title: str,
    *,
    required: bool,
) -> dict[str, Any] | None:
    matches = [item for item in listing if item.get("title") == title]
    if len(matches) > 1:
        raise RuntimeError(f"duplicate Stage 2 session title: {title}")
    if not matches:
        if required:
            raise RuntimeError(f"missing Stage 2 session title: {title}")
        return None
    return gateway.get_session(str(matches[0]["id"]))


def _expect_session(
    session: dict[str, Any],
    *,
    title: str,
    interaction_mode: str,
    character_id: str | None,
    read_memory: bool | None,
    write_memory: bool | None,
) -> None:
    if session.get("title") != title:
        raise RuntimeError("hydrated session title did not match discovery title")
    if session.get("interaction_mode") != interaction_mode:
        raise RuntimeError(f"Stage 2 session has wrong interaction mode: {title}")
    if session.get("character_id") != character_id:
        raise RuntimeError(f"Stage 2 session has wrong character owner: {title}")
    if read_memory is not None and session.get("read_memory") is not read_memory:
        raise RuntimeError(f"Stage 2 session has wrong read policy: {title}")
    if write_memory is not None and session.get("write_memory") is not write_memory:
        raise RuntimeError(f"Stage 2 session has wrong write policy: {title}")
    if session.get("shared_memory_access") != "none":
        raise RuntimeError(f"Stage 2 session has shared memory enabled: {title}")


def _fixture_record(
    gateway: Stage2Gateway,
    session_id: str,
    *,
    run_id: str,
    owner_label: str,
    owner_type: str,
    owner_id: str,
    required: bool,
) -> _FixtureRecord | None:
    expected = marker_memory(run_id, owner_label)
    listing = gateway.list_memory(session_id)
    records = listing.get("records")
    if not isinstance(records, list):
        raise RuntimeError("memory listing did not return records")
    matches = [
        item
        for item in records
        if isinstance(item, dict)
        and item.get("content") == expected
        and item.get("status") == "active"
    ]
    if len(matches) > 1:
        raise RuntimeError(f"duplicate active Stage 2 fixture memories exist for {owner_label}")
    if not matches:
        if required:
            raise RuntimeError(f"missing active Stage 2 fixture memory for {owner_label}")
        return None
    record = matches[0]
    if record.get("owner_type") != owner_type or record.get("owner_id") != owner_id:
        raise RuntimeError(f"Stage 2 fixture memory has wrong owner: {owner_label}")
    revision = int(record.get("revision") or 0)
    if revision < 1:
        raise RuntimeError(f"Stage 2 fixture memory has invalid revision: {owner_label}")
    return _FixtureRecord(
        id=str(record["id"]),
        revision=revision,
        owner_type=owner_type,
        owner_id=owner_id,
    )


def _validate_maya_pilot(
    gateway: Stage2Gateway,
    session: dict[str, Any],
    config: Stage2PrepareConfig,
) -> tuple[dict[str, Any], list[str], list[str]]:
    _expect_session(
        session,
        title=MAYA_PILOT_TITLE,
        interaction_mode="character",
        character_id=config.maya_character_id,
        read_memory=True,
        write_memory=False,
    )
    state = gateway.memory_state(str(session["id"]))
    if state.get("owner_type") != "character" or state.get("owner_id") != config.maya_character_id:
        raise RuntimeError("Maya pilot memory state resolved the wrong owner")
    candidates = memory_candidate_ids(gateway.list_candidates(str(session["id"])))
    return state, snapshot_item_ids(state), candidates


def _fully_cleaned_report(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    listing: list[dict[str, Any]],
    maya_pilot: dict[str, Any],
    *,
    dry_run: bool,
) -> Stage2Report:
    state, active_snapshot_ids, candidates = _validate_maya_pilot(gateway, maya_pilot, config)
    checks = [
        Stage2Check(
            id="discovery.sessions",
            status="pass",
            summary="Only the retained Maya pilot session remains from the Stage 2 fixture set.",
            observed={
                "retained_maya_pilot_session_id": maya_pilot.get("id"),
                "temporary_session_count": 0,
                "dry_run": dry_run,
            },
        ),
        Stage2Check(
            id="discovery.pilot_policy",
            status="pass",
            summary="Retained Maya pilot remains read-only with shared memory disabled.",
            observed={
                "read_memory": True,
                "write_memory": False,
                "shared_memory_access": "none",
                "pending_candidate_count": len(candidates),
            },
        ),
        Stage2Check(
            id="cleanup.idempotent",
            status="pass",
            summary="No temporary Stage 2 sessions remain; cleanup is already complete.",
            observed={
                "active_snapshot_count": len(active_snapshot_ids),
                "known_stage2_session_count": len(
                    [
                        item
                        for item in listing
                        if item.get("title") in set(TEMPORARY_TITLES + (MAYA_PILOT_TITLE,))
                    ]
                ),
            },
        ),
    ]
    return _report(
        config,
        checks,
        {
            "dry_run": dry_run,
            "maya_snapshot_active_count": len(active_snapshot_ids),
            "snapshot_id": state.get("snapshot_id"),
        },
        session_id=str(maya_pilot["id"]),
    )


def discover_stage2_cleanup(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    *,
    apply: bool = False,
) -> Stage2Report:
    try:
        listing = _sessions(gateway.list_sessions())
        maya_pilot = _unique_by_title(gateway, listing, MAYA_PILOT_TITLE, required=True)
        assert maya_pilot is not None
        present_temporary = [
            title
            for title in TEMPORARY_TITLES
            if any(item.get("title") == title for item in listing)
        ]
        if not present_temporary:
            return _fully_cleaned_report(
                gateway,
                config,
                listing,
                maya_pilot,
                dry_run=not apply,
            )
        if set(present_temporary) != set(TEMPORARY_TITLES):
            raise RuntimeError("partial Stage 2 session set is ambiguous")

        maya_setup = _unique_by_title(gateway, listing, MAYA_SETUP_TITLE, required=True)
        alex_setup = _unique_by_title(gateway, listing, ALEX_SETUP_TITLE, required=True)
        system_setup = _unique_by_title(gateway, listing, SYSTEM_SETUP_TITLE, required=True)
        alex_control = _unique_by_title(gateway, listing, ALEX_CONTROL_TITLE, required=True)
        assert maya_setup and alex_setup and system_setup and alex_control

        _expect_session(
            maya_setup,
            title=MAYA_SETUP_TITLE,
            interaction_mode="character",
            character_id=config.maya_character_id,
            read_memory=False,
            write_memory=True,
        )
        _expect_session(
            alex_setup,
            title=ALEX_SETUP_TITLE,
            interaction_mode="character",
            character_id=config.alex_character_id,
            read_memory=False,
            write_memory=True,
        )
        _expect_session(
            system_setup,
            title=SYSTEM_SETUP_TITLE,
            interaction_mode="system",
            character_id=None,
            read_memory=False,
            write_memory=False,
        )
        _expect_session(
            alex_control,
            title=ALEX_CONTROL_TITLE,
            interaction_mode="character",
            character_id=config.alex_character_id,
            read_memory=True,
            write_memory=False,
        )
        maya_state, maya_snapshot_ids, maya_candidates = _validate_maya_pilot(
            gateway,
            maya_pilot,
            config,
        )

        maya = _fixture_record(
            gateway,
            str(maya_setup["id"]),
            run_id=config.run_id,
            owner_label="maya",
            owner_type="character",
            owner_id=config.maya_character_id,
            required=False,
        )
        alex = _fixture_record(
            gateway,
            str(alex_setup["id"]),
            run_id=config.run_id,
            owner_label="alex",
            owner_type="character",
            owner_id=config.alex_character_id,
            required=True,
        )
        system = _fixture_record(
            gateway,
            str(system_setup["id"]),
            run_id=config.run_id,
            owner_label="system",
            owner_type="system",
            owner_id="system-assistant",
            required=True,
        )
        assert alex and system
        if {alex.id, system.id} & set(maya_snapshot_ids):
            raise RuntimeError("cross-owner fixture appears in Maya pilot snapshot")
        if maya and maya.id not in set(maya_snapshot_ids):
            raise RuntimeError("active Maya fixture is missing from Maya pilot snapshot")

        checks = [
            Stage2Check(
                id="discovery.sessions",
                status="pass",
                summary="Unique Stage 2 fixture sessions and retained Maya pilot were discovered.",
                observed={
                    "maya_setup_session_id": maya_setup.get("id"),
                    "alex_setup_session_id": alex_setup.get("id"),
                    "system_setup_session_id": system_setup.get("id"),
                    "alex_control_session_id": alex_control.get("id"),
                    "retained_maya_pilot_session_id": maya_pilot.get("id"),
                    "temporary_session_count": 4,
                },
            ),
            Stage2Check(
                id="discovery.fixture_markers",
                status="pass",
                summary="Exact Stage 2 fixture markers resolved to unique owner-scoped records.",
                observed={
                    "marker_hashes": {
                        owner: marker_hash(marker(config.run_id, owner))
                        for owner in ("maya", "alex", "system")
                    },
                    "maya_memory_id": maya.id if maya else None,
                    "alex_memory_id": alex.id,
                    "system_memory_id": system.id,
                    "maya_already_absent": maya is None,
                    "owner_dimensions": {
                        "maya": f"character/{config.maya_character_id}",
                        "alex": f"character/{config.alex_character_id}",
                        "system": "system/system-assistant",
                    },
                },
            ),
            Stage2Check(
                id="discovery.pilot_policy",
                status="pass",
                summary="Retained Maya pilot remains read-only with shared memory disabled.",
                observed={
                    "read_memory": True,
                    "write_memory": False,
                    "shared_memory_access": "none",
                    "active_snapshot_count": len(maya_snapshot_ids),
                    "pending_candidate_count": len(maya_candidates),
                },
            ),
        ]
        if not apply:
            checks.append(
                Stage2Check(
                    id="cleanup.plan",
                    status="review",
                    summary="Dry-run discovered an exact cleanup plan; rerun with --apply to mutate.",
                    observed={
                        "would_delete_records": len([item for item in (maya, alex, system) if item]),
                        "would_delete_temporary_sessions": 4,
                        "would_retain_maya_pilot": True,
                    },
                )
            )
            return _report(
                config,
                checks,
                {"dry_run": True, "maya_snapshot_active_count": len(maya_snapshot_ids)},
                session_id=str(maya_pilot["id"]),
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
            maya_pilot_session_id=str(maya_pilot["id"]),
            alex_pilot_session_id=str(alex_control["id"]),
            maya_segment_id=str(maya_pilot.get("active_segment_id") or "unknown"),
            maya_identity_hash=str(maya_pilot.get("effective_identity_hash") or ("0" * 64)),
            maya_snapshot_id=str(maya_state.get("snapshot_id") or "unknown"),
            maya_snapshot_revision=int(maya_state.get("snapshot_revision") or 1),
            maya_memory_id=maya.id if maya else "stage2-maya-synthetic-already-absent",
            alex_memory_id=alex.id,
            system_memory_id=system.id,
            baseline_maya_record_ids=memory_record_ids(gateway.list_memory(str(maya_pilot["id"]))),
            baseline_maya_candidate_ids=maya_candidates,
            marker_hashes={
                owner: marker_hash(marker(config.run_id, owner))
                for owner in ("maya", "alex", "system")
            },
            prepare_checks=checks,
            prepare_metrics=Stage2Metrics(snapshot_record_count=len(maya_snapshot_ids)),
        )
        cleanup_and_verify_forget(gateway, checkpoint, config.token_budget)
        checks.append(
            Stage2Check(
                id="cleanup.apply",
                status="pass",
                summary="Discovered Stage 2 fixture records and temporary sessions were cleaned up.",
                observed={
                    "deleted_or_previously_deleted_records": 3,
                    "deleted_temporary_sessions": 4,
                    "retained_maya_pilot": True,
                },
            )
        )
        return _report(
            config,
            checks,
            {"dry_run": False, "maya_snapshot_active_count": len(maya_snapshot_ids)},
            session_id=str(maya_pilot["id"]),
        )
    except Exception as exc:
        return _blocked(
            config,
            "discovery.blocked",
            " ".join(str(exc).strip().split())[:500] or exc.__class__.__name__,
        )


__all__ = ["discover_stage2_cleanup"]
