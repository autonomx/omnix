"""Lease-backed worker for reusable-world topic jobs."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from app.rpg.session.genesis.world_forge_generation import WorldForgeTopicGenerator

from .generation_coordinator import execute_claimed_world_topic_job
from .generation_jobs import WORLD_TOPIC_RESOURCE_CLASS

_DEFAULT_LEASE_SECONDS = 3600
_MAX_WORLD_GENERATION_WORKERS = 4
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
    return execute_claimed_world_topic_job(
        job=job,
        worker_id=worker_id,
        generator=generator,
        database=db,
    )


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
        except Exception:
            _LOGGER.exception("RPG world-generation worker slot failed")
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
    try:
        state = _WorkerPoolState()
        workers = [
            threading.Thread(
                target=_worker_loop,
                args=(slot, database, state),
                daemon=True,
                name=f"omnix-rpg-world-generation-{slot}",
            )
            for slot in range(1, _MAX_WORLD_GENERATION_WORKERS + 1)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
    finally:
        with _worker_lock:
            _worker_active = False


def kick_world_generation_worker(*, database: Any | None = None) -> bool:
    """Start one bounded four-thread worker pool when none is already active."""

    global _worker_active
    with _worker_lock:
        if _worker_active:
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
