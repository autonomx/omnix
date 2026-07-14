"""Atomic PostgreSQL persistence for one foreground RPG turn."""

from __future__ import annotations

from typing import Any

from .database import PostgresDatabase, default_database
from .identity_service import bootstrap_local_tenant
from .rpg_repository import canonical_json
from .unit_of_work import unit_of_work


def persist_foreground_turn(
    *,
    session_id: str,
    player_input: str,
    session: dict[str, Any],
    result: dict[str, Any],
    event: dict[str, Any],
    submission_id: str,
    database: PostgresDatabase | None = None,
) -> dict[str, Any]:
    """Commit campaign, turn, interaction, job, submission, and outbox atomically."""

    if not submission_id:
        submission_id = f"submission:{event.get('interaction_id') or event.get('sequence')}"
    interaction_id = str(event.get("interaction_id") or "").strip()
    if not interaction_id:
        raise ValueError("foreground RPG turn requires an interaction_id")
    state_revision = int(event.get("state_revision") or 0)
    if state_revision < 1:
        raise ValueError("foreground RPG turn requires a positive state revision")
    expected_revision = state_revision - 1
    turn_id = _campaign_record_id("turn", session_id, state_revision)
    interaction_record_id = _campaign_record_id("interaction", session_id, state_revision)

    from app.gateway.rpg_foreground_turn_record import build_foreground_turn_record

    response_source = dict(result)
    response_source["submission_id"] = submission_id
    response_source["interaction_id"] = interaction_id
    compact_response = build_foreground_turn_record(
        response_source,
        session_id=session_id,
        submission_id=submission_id,
        command=player_input,
    )

    db = database or default_database()
    context = bootstrap_local_tenant(db)
    with unit_of_work(db) as work:
        submission = work.connection.execute(
            """
            SELECT status, claim_token, job_id, response, execution_started_at
              FROM omnix_rpg_foreground_submissions
             WHERE workspace_id = %s AND session_id = %s AND submission_id = %s
             FOR UPDATE
            """,
            (context.workspace_id, session_id, submission_id),
        ).fetchone()
        if submission is None:
            claim = work.foreground_submissions.claim(
                context,
                session_id=session_id,
                submission_id=submission_id,
                lease_seconds=600,
            )
            claim_token = str(claim.get("claim_token") or "")
            if not claim_token:
                raise RuntimeError("foreground submission claim token was not created")
            if not work.foreground_submissions.start_execution(
                context,
                session_id=session_id,
                submission_id=submission_id,
                claim_token=claim_token,
            ):
                raise RuntimeError("foreground submission execution could not start")
            job_id = None
        else:
            status = str(submission[0])
            if status == "completed" and submission[3] is not None:
                work.rollback()
                return {
                    "idempotent_replay": True,
                    "response": dict(submission[3]),
                    "interaction_id": interaction_id,
                    "submission_id": submission_id,
                }
            if status != "claimed":
                raise RuntimeError(f"foreground submission is not claimable: {status}")
            claim_token = str(submission[1])
            job_id = str(submission[2]) if submission[2] is not None else None
            if submission[4] is None:
                if not work.foreground_submissions.start_execution(
                    context,
                    session_id=session_id,
                    submission_id=submission_id,
                    claim_token=claim_token,
                ):
                    raise RuntimeError("foreground submission execution fence was rejected")

        campaign = work.rpg.get_campaign(context, session_id, for_update=True)
        if campaign is None:
            raise RuntimeError(
                f"RPG campaign {session_id} was not initialized in PostgreSQL before the turn"
            )

        persisted = work.rpg.commit_turn(
            context,
            campaign_id=session_id,
            turn_id=turn_id,
            submission_id=submission_id,
            interaction_id=interaction_record_id,
            expected_revision=expected_revision,
            command={"player_input": player_input},
            next_state=session,
            canonical_effects=_canonical_effects(result),
            interaction_event=event,
            compact_response=compact_response,
            engine_version=str(campaign["engine_version"]),
            schema_version=str(campaign["schema_version"]),
            create_snapshot=bool(event.get("stateful") is not False),
            snapshot_id=f"snapshot:{session_id}:{state_revision}",
        )

        completed_job: dict[str, Any] | None = None
        if job_id:
            job = work.jobs.get_job(context, job_id)
            if job is None:
                raise RuntimeError(f"foreground RPG job disappeared: {job_id}")
            if job["status"] == "completed":
                completed_job = job
            else:
                lease_owner = str(job.get("lease_owner") or "")
                lease_token = str(job.get("lease_token") or "")
                metadata_value = job.get("metadata")
                metadata = metadata_value if isinstance(metadata_value, dict) else {}
                contract_value = metadata.get("compat_contract")
                contract = contract_value if isinstance(contract_value, dict) else {}
                compat_value = contract.get("compat")
                compat = compat_value if isinstance(compat_value, dict) else {}
                if compat.get("record_only") is True:
                    completed_job = work.jobs.complete_record_only(
                        context,
                        job_id=job_id,
                        output_refs=[
                            {
                                "type": "rpg_turn_response",
                                "module": "rpg",
                                "session_id": session_id,
                                "submission_id": submission_id,
                                "interaction_id": interaction_id,
                                "turn_response": compact_response,
                                "source": "postgresql_foreground_transaction",
                            }
                        ],
                        progress={"current": 1, "total": 1, "message": "completed"},
                    )
                elif not lease_owner or not lease_token:
                    raise RuntimeError(f"foreground RPG job has no active lease: {job_id}")
                else:
                    completed_job = work.jobs.complete(
                        context,
                        job_id=job_id,
                        worker_id=lease_owner,
                        lease_token=lease_token,
                        output_refs=[
                            {
                                "type": "rpg_turn_response",
                                "module": "rpg",
                                "session_id": session_id,
                                "submission_id": submission_id,
                                "interaction_id": interaction_id,
                                "turn_response": compact_response,
                                "source": "postgresql_foreground_transaction",
                            }
                        ],
                        progress={"current": 1, "total": 1, "message": "completed"},
                    )

        if not work.foreground_submissions.complete(
            context,
            session_id=session_id,
            submission_id=submission_id,
            claim_token=claim_token,
            interaction_id=interaction_record_id,
            response=compact_response,
        ):
            raise RuntimeError("foreground RPG submission result could not be finalized")

        work.audit.append(
            context,
            aggregate_type="rpg_turn",
            aggregate_id=turn_id,
            action="rpg.turn_committed",
            payload={
                "campaign_id": session_id,
                "submission_id": submission_id,
                "interaction_id": interaction_id,
                "interaction_record_id": interaction_record_id,
                "resulting_revision": state_revision,
            },
        )
        work.commit()

    return {
        "idempotent_replay": bool(persisted.get("idempotent_replay")),
        "campaign": persisted.get("campaign"),
        "turn": persisted.get("turn"),
        "snapshot": persisted.get("snapshot"),
        "job": completed_job,
        "response": compact_response,
        "submission_id": submission_id,
        "interaction_id": interaction_id,
        "interaction_record_id": interaction_record_id,
        "transaction": "postgresql_unit_of_work",
    }


def _campaign_record_id(kind: str, session_id: str, state_revision: int) -> str:
    """Build a globally unique PostgreSQL record id from campaign-local counters."""
    return f"{kind}:{session_id}:{state_revision}"


def _canonical_effects(result: dict[str, Any]) -> dict[str, Any]:
    for source in (
        result,
        result.get("result") if isinstance(result.get("result"), dict) else {},
        result.get("authoritative") if isinstance(result.get("authoritative"), dict) else {},
    ):
        value = source.get("canonical_effects")
        if isinstance(value, dict):
            return value
        value = source.get("effects")
        if isinstance(value, dict):
            return value
    return {"result_hash_input": canonical_json(_bounded_result(result))}


def _bounded_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"session", "simulation_state", "runtime_state", "foreground_job"}
    }
