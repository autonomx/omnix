"""A foreground RPG turn executed once per submission (F2).

The turn route names each turn by its submission id. The submission's durable claim (``omnix_rpg_foreground_submissions``)
makes it exactly once: the first request claims it and executes the turn, a repeat replays the response the claim
recorded, and a request that finds the claim held waits for it. Execution starts behind a fence: once the turn has
started, an expired claim is never taken over, so a turn is never run twice. The commit completes the claim in the
turn's own transaction (``rpg_turn_service.persist_foreground_turn``), under the claim this module carries
(``foreground_context.foreground_claim``).

No job is written for the turn: the claim already holds what a repeat needs, and the turn's own records (the turn, its
interaction, its metrics) hold what an operator reads. The job mirror that recorded each turn as a second, record-only
job cost a third of the turn's statements (F2).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable
import uuid

from app.config.env import env_str as _env_str
from app.apps.rpg.foundation.performance_trace import rpg_pipeline_span
from app.apps.rpg.session.foreground_turn_record import build_foreground_turn_record
from app.apps.rpg.session.jobs.foreground_context import (
    DIRECT_RPG_SUBMISSION_ID,
    ForegroundClaim,
    foreground_claim,
)


def default_submission_store() -> Any:
    """The durable claims: PostgreSQL's when the runtime is, else this process's own."""
    from app.persistence.runtime import uses_postgresql_runtime

    if uses_postgresql_runtime():
        from app.apps.rpg.foundation.persistence.foreground_submissions import (
            default_postgres_foreground_submission_store,
        )

        return default_postgres_foreground_submission_store()
    from app.apps.rpg.session.jobs.foreground_submission_store import InMemoryForegroundSubmissionStore

    return InMemoryForegroundSubmissionStore(None)


def execute_foreground_turn(
    apply_turn: Callable[..., dict[str, Any]],
    session_id: str,
    command: str,
    *args: Any,
    submission_id: str | None = None,
    submissions: Any | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run ``apply_turn`` once for this submission, or replay the response its claim recorded."""
    resolved = str(submission_id or f"submit:{uuid.uuid4().hex}").strip()
    store = submissions if submissions is not None else default_submission_store()
    submission_token = DIRECT_RPG_SUBMISSION_ID.set(resolved)
    try:
        with rpg_pipeline_span("turn.idempotency_claim") as claim_span:
            claim, replay = _acquire_claim(store, session_id=session_id, submission_id=resolved)
            claim_span["owner"] = getattr(claim, "owner", None)
            claim_span["replay"] = replay is not None
        if replay is not None:
            return replay
        with rpg_pipeline_span("turn.authoritative_execution_fence") as fence_span:
            replay = _begin_execution(store, claim, session_id=session_id, submission_id=resolved)
            fence_span["replay"] = replay is not None
        if replay is not None:
            return replay
        executing = ForegroundClaim(session_id, resolved, str(claim.claim_token))
        try:
            with foreground_claim(executing):
                result = apply_turn(session_id, command, *args, **kwargs)
        except Exception as exc:
            store.fail(session_id, resolved, claim.claim_token, str(exc) or "RPG turn failed")
            raise
        finalized = {**result, "submission_id": resolved}
        if not executing.committed:
            # A turn that stopped before a commit (a refusal, a turn that saves nothing) finalizes its claim here,
            # so a repeat replays it instead of running again; a committed turn's commit completed it.
            with rpg_pipeline_span("turn.idempotency_result_finalize"):
                store.complete(session_id, resolved, claim.claim_token, build_foreground_turn_record(
                    finalized, session_id=session_id, submission_id=resolved, command=command))
        return finalized
    finally:
        DIRECT_RPG_SUBMISSION_ID.reset(submission_token)


def _acquire_claim(store: Any, *, session_id: str, submission_id: str) -> tuple[Any, dict[str, Any] | None]:
    claim = store.claim(session_id, submission_id, lease_seconds=_lease_seconds())
    if not claim.owner and claim.status == "claimed":
        claim = store.wait_for_terminal_or_claim(
            session_id, submission_id, timeout_seconds=_wait_seconds(), lease_seconds=_lease_seconds())
    recovered = _recovered(claim)
    if recovered is not None:
        return claim, recovered
    if getattr(claim, "status", "") == "failed":
        raise RuntimeError(getattr(claim, "error", None) or "foreground submission failed")
    if getattr(claim, "owner", False):
        return claim, None
    raise TimeoutError(f"foreground submission {submission_id} for {session_id} did not reach a terminal state")


def _begin_execution(store: Any, claim: Any, *, session_id: str, submission_id: str) -> dict[str, Any] | None:
    if store.mark_execution_started(session_id, submission_id, claim.claim_token):
        return None
    terminal = store.wait_for_terminal(session_id, submission_id, timeout_seconds=_wait_seconds())
    recovered = _recovered(terminal)
    if recovered is not None:
        return recovered
    if getattr(terminal, "status", "") == "failed":
        raise RuntimeError(getattr(terminal, "error", None) or "foreground submission failed")
    raise TimeoutError(f"foreground submission ownership changed before execution for {submission_id}")


def _recovered(claim: Any) -> dict[str, Any] | None:
    if getattr(claim, "status", "") != "completed" or not isinstance(getattr(claim, "result", None), dict):
        return None
    recovered = deepcopy(claim.result)
    recovered["submission_id"] = str(getattr(claim, "submission_id", "") or recovered.get("submission_id") or "")
    recovered["idempotent_replay"] = True
    return recovered


def _bounded_seconds(name: str, default: str) -> float:
    try:
        return max(0.1, min(600.0, float(_env_str(name, default))))
    except (TypeError, ValueError):
        return float(default)


def _wait_seconds() -> float:
    return _bounded_seconds("OMNIX_RPG_SUBMISSION_WAIT_SECONDS", "120")


def _lease_seconds() -> float:
    return _bounded_seconds("OMNIX_RPG_SUBMISSION_LEASE_SECONDS", "30")


__all__ = ["default_submission_store", "execute_foreground_turn"]
