"""How a run ends: one place sets its terminal status, desired state and error.

Each ending goes through ``repository.update_state``, so a lease-bound repository still fences a worker's
write with its lease, and the revision check still refuses a stale writer.
"""
from __future__ import annotations

from typing import Any

from .contracts import AgentRunSnapshot

ERROR_LIMIT = 2000


def _worker(worker_id: str | None, lease_token: str | None) -> dict[str, str]:
    """The worker's credentials, named only when given: an unnamed worker writes as Omnix itself."""
    credentials = {"worker_id": worker_id, "lease_token": lease_token}
    return {key: value for key, value in credentials.items() if value is not None}


def fail_run(
    repository: Any,
    run_id: str,
    *,
    expected_revision: int,
    error: str,
    worker_id: str | None = None,
    lease_token: str | None = None,
) -> AgentRunSnapshot:
    """The run failed and is not to run again: ``failed``, desired ``cancelled``, its error cut to ERROR_LIMIT."""
    return repository.update_state(
        run_id,
        expected_revision=expected_revision,
        status="failed",
        desired_state="cancelled",
        last_error=str(error)[:ERROR_LIMIT],
        **_worker(worker_id, lease_token),
    )


def complete_run(
    repository: Any,
    run_id: str,
    *,
    expected_revision: int,
    worker_id: str | None = None,
) -> AgentRunSnapshot:
    """The run passed: ``completed``, with no error."""
    return repository.update_state(
        run_id,
        expected_revision=expected_revision,
        status="completed",
        last_error=None,
        **_worker(worker_id, None),
    )


def cancel_run(
    repository: Any,
    run_id: str,
    *,
    expected_revision: int,
    worker_id: str | None = None,
    lease_token: str | None = None,
    error: str | None = None,
) -> AgentRunSnapshot:
    """The run was stopped on request: ``cancelled``, desired ``cancelled``.

    ``error`` records why the stop itself went wrong (a cancel command that failed still ends the run).
    """
    reason = {} if error is None else {"last_error": str(error)[:ERROR_LIMIT]}
    return repository.update_state(
        run_id,
        expected_revision=expected_revision,
        status="cancelled",
        desired_state="cancelled",
        **reason,
        **_worker(worker_id, lease_token),
    )


__all__ = ["ERROR_LIMIT", "cancel_run", "complete_run", "fail_run"]
