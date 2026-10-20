"""Job submission for voice code that creates jobs outside ``POST /api/jobs`` (batch runs, API clients).

A job created here passes the same checks as one the jobs API creates: the
handler registry's submission policy and input model, then the job store. The
registry belongs to the composed gateway, so its routes and workers name it
here (``use_job_registry``); without one, the voice feature's own submission
policy still applies.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

_registry_source: Callable[[], Any] | None = None


def use_job_registry(source: Callable[[], Any]) -> None:
    """Where to find the composed job handler registry (read at each submission)."""
    global _registry_source
    _registry_source = source


def validated_request(request: dict[str, Any]) -> Any:
    from app.jobs.models import CreateJobRequest

    from .feature import voice_submission_defaults

    value = CreateJobRequest.model_validate(request)
    registry = _registry_source() if _registry_source is not None else None
    if registry is not None:
        return registry.validate_submission(value)
    return voice_submission_defaults(value)


def submit_job(request: dict[str, Any], *, job_store: Any = None, idempotency_key: str = "") -> Any:
    """Create the job in the current tenant; ``job_store`` defaults to the process's job store.

    With an ``idempotency_key`` the same key returns the same job (``create_job_once``).
    """
    if job_store is None:
        from app.jobs.store import default_job_store

        job_store = default_job_store()
    validated = validated_request(request)
    if idempotency_key and hasattr(job_store, "create_job_once"):
        return job_store.create_job_once(validated, idempotency_key=idempotency_key)
    return job_store.create_job(validated)


__all__ = ["submit_job", "use_job_registry", "validated_request"]
