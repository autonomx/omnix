"""Lease-backed worker for reusable-world topic jobs."""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.rpg.session.genesis.world_forge_generation import WorldForgeTopicGenerator

from .generation_coordinator import execute_claimed_world_topic_job
from .generation_diagnostics import log_world_generation_event
from .generation_jobs import WORLD_TOPIC_RESOURCE_CLASS

_DEFAULT_LEASE_SECONDS = 3600
_DEFAULT_MAX_WORLD_GENERATION_WORKERS = 4
_LMSTUDIO_MAX_WORLD_GENERATION_WORKERS = 1
_LOGGER = logging.getLogger(__name__)
_worker_lock = threading.Lock()
_worker_active = False


@dataclass
class _WorkerPoolState:
    condition: threading.Condition = field(default_factory=threading.Condition)
    calls_in_progress: int = 0
    completion_generation: int = 0
    stop: bool = False


def _database(value: Any | None) -> Any:
    if value is not None:
        return value
    from app.persistence.database import default_database

    return default_database()


def _provider_key(value: Any) -> str:
    provider = str(value or "").strip().casefold()
    if provider.startswith("llm:"):
        provider = provider.split(":", 1)[1]
    return provider


def _configured_world_forge_provider(
    environ: Mapping[str, str] | None = None,
) -> str:
    env = environ or os.environ
    dedicated = _provider_key(env.get("OMNIX_RPG_WORLD_FORGE_PROVIDER"))
    if dedicated:
        return dedicated
    try:
        from app.platform.effective_defaults import (
            effective_llm_route,
            load_effective_profile,
        )

        profile = load_effective_profile()
        provider_id, _model_id = effective_llm_route(
            profile,
            "rpg",
            "rpg.world_forge.generate",
        )
        return _provider_key(provider_id)
    except Exception:
        return ""


def world_generation_worker_limit(
    environ: Mapping[str, str] | None = None,
) -> int:
    """Return a safe worker count for the configured World Forge provider.

    LM Studio commonly exposes one model channel even when the application can queue
    several jobs. Serializing provider calls avoids the channel resets that otherwise
    turn healthy topic jobs into repeated transient failures. Operators with an LM
    Studio deployment configured for parallel inference can explicitly raise the
    worker count through ``OMNIX_RPG_WORLD_GENERATION_WORKERS``.
    """

    env = environ or os.environ
    override = str(env.get("OMNIX_RPG_WORLD_GENERATION_WORKERS") or "").strip()
    if override:
        try:
            return max(1, min(int(override), _DEFAULT_MAX_WORLD_GENERATION_WORKERS))
        except ValueError:
            _LOGGER.warning(
                "Ignoring invalid OMNIX_RPG_WORLD_GENERATION_WORKERS=%r",
                override,
            )
    if _configured_world_forge_provider(env) == "lmstudio":
        return _LMSTUDIO_MAX_WORLD_GENERATION_WORKERS
    return _DEFAULT_MAX_WORLD_GENERATION_WORKERS


def _job_fields(job: Mapping[str, Any], *, worker_id: str) -> dict[str, Any]:
    payload = dict(job.get("input_payload") or {})
    settings = dict(payload.get("settings") or {})
    metadata = dict(job.get("metadata") or {})
    return {
        "worker_id": worker_id,
        "attempt_count": job.get("attempt_count"),
        "max_attempts": job.get("max_attempts"),
        "status": job.get("status"),
        "provider_route": settings.get("provider_route"),
        "model": settings.get("model"),
        "generator_version": settings.get("generator_version"),
        "prompt_version": settings.get("prompt_version"),
        "dependency_ids": metadata.get("dependency_ids") or [],
    }


def run_world_generation_worker_once(
    *,
    worker_id: str = "rpg-world-generation:local",
    database: Any | None = None,
    generator: WorldForgeTopicGenerator | None = None,
) -> dict[str, Any] | None:
    """Claim and execute one world-topic job without touching campaign Genesis jobs."""

    db = _database(database)
    from app.persistence.identity_service import bootstrap_local_tenant
    from app.persistence.unit_of_work import unit_of_work

    context = bootstrap_local_tenant(db)
    with unit_of_work(db) as work:
        job = work.jobs.claim_next(
            context,
            worker_id=worker_id,
            resource_classes=[WORLD_TOPIC_RESOURCE_CLASS],
            lease_seconds=_DEFAULT_LEASE_SECONDS,
        )
        if job is None:
            work.rollback()
            return None
        job = work.jobs.mark_running(
            context,
            job_id=job["id"],
            worker_id=worker_id,
            lease_token=str(job["lease_token"]),
        )
        work.commit()

    metadata = dict(job.get("metadata") or {})
    run_id = str(metadata.get("run_id") or "")
    world_id = str(metadata.get("world_id") or "")
    topic_id = str(metadata.get("topic_id") or "")
    log_world_generation_event(
        "world_generation.job_started",
        world_id=world_id,
        run_id=run_id,
        topic_id=topic_id,
        job_id=str(job.get("id") or ""),
        fields=_job_fields(job, worker_id=worker_id),
    )
    result = execute_claimed_world_topic_job(
        job=job,
        worker_id=worker_id,
        generator=generator,
        database=db,
    )
    status = str(result.get("status") or "unknown")
    ok = bool(result.get("ok"))
    fields = {
        **_job_fields(dict(result.get("job") or job), worker_id=worker_id),
        "result_status": status,
        "detail": result.get("detail"),
    }
    log_world_generation_event(
        "world_generation.job_completed" if ok else "world_generation.job_attempt_failed",
        level="info" if ok else "error" if status == "failed" else "warning",
        world_id=world_id,
        run_id=run_id,
        topic_id=topic_id,
        job_id=str(job.get("id") or ""),
        fields=fields,
        error=result.get("detail") if not ok else None,
    )
    return result


def _worker_loop(
    slot: int,
    database: Any | None,
    state: _WorkerPoolState,
) -> None:
    worker_id = f"rpg-world-generation:local:{slot}"
    while True:
        with state.condition:
            if state.stop:
                return
            state.calls_in_progress += 1
        try:
            result = run_world_generation_worker_once(
                worker_id=worker_id,
                database=database,
            )
        except Exception as exc:
            _LOGGER.exception("RPG world-generation worker slot failed")
            log_world_generation_event(
                "world_generation.worker_slot_failed",
                level="error",
                fields={"slot": slot, "worker_id": worker_id},
                error=exc,
            )
            result = None
        with state.condition:
            state.calls_in_progress -= 1
            if result is not None:
                state.completion_generation += 1
                state.condition.notify_all()
                continue

            observed_generation = state.completion_generation
            if state.calls_in_progress == 0:
                state.stop = True
                state.condition.notify_all()
                return
            state.condition.wait_for(
                lambda: state.stop
                or state.completion_generation != observed_generation
            )
            if state.stop:
                return


def _worker_pool_loop(database: Any | None) -> None:
    global _worker_active
    worker_limit = world_generation_worker_limit()
    try:
        state = _WorkerPoolState()
        _LOGGER.info(
            "Starting RPG world-generation worker pool with %s slot(s)",
            worker_limit,
        )
        log_world_generation_event(
            "world_generation.worker_pool_started",
            fields={
                "worker_limit": worker_limit,
                "configured_provider": _configured_world_forge_provider(),
            },
        )
        workers = [
            threading.Thread(
                target=_worker_loop,
                args=(slot, database, state),
                daemon=True,
                name=f"omnix-rpg-world-generation-{slot}",
            )
            for slot in range(1, worker_limit + 1)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
    except Exception as exc:
        log_world_generation_event(
            "world_generation.worker_pool_failed",
            level="error",
            fields={"worker_limit": worker_limit},
            error=exc,
        )
        raise
    finally:
        log_world_generation_event(
            "world_generation.worker_pool_stopped",
            fields={"worker_limit": worker_limit},
        )
        with _worker_lock:
            _worker_active = False


def kick_world_generation_worker(*, database: Any | None = None) -> bool:
    """Start one bounded provider-aware worker pool when none is already active."""

    global _worker_active
    with _worker_lock:
        if _worker_active:
            log_world_generation_event(
                "world_generation.worker_pool_already_active",
                fields={"worker_limit": world_generation_worker_limit()},
            )
            return False
        _worker_active = True
    thread = threading.Thread(
        target=_worker_pool_loop,
        args=(database,),
        daemon=True,
        name="omnix-rpg-world-generation-supervisor",
    )
    thread.start()
    return True
