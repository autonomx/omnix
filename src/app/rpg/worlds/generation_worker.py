"""Lease-backed worker for reusable-world topic jobs."""
from __future__ import annotations

import threading
from typing import Any

from app.rpg.session.genesis.world_forge_generation import WorldForgeTopicGenerator

from .generation_coordinator import execute_claimed_world_topic_job
from .generation_jobs import WORLD_TOPIC_RESOURCE_CLASS

_DEFAULT_LEASE_SECONDS = 3600
_worker_lock = threading.Lock()
_worker_active = False


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


def _worker_loop(database: Any | None) -> None:
    global _worker_active
    try:
        while run_world_generation_worker_once(database=database) is not None:
            pass
    finally:
        with _worker_lock:
            _worker_active = False


def kick_world_generation_worker(*, database: Any | None = None) -> bool:
    """Start one local draining worker when another is not already active."""

    global _worker_active
    with _worker_lock:
        if _worker_active:
            return False
        _worker_active = True
    thread = threading.Thread(
        target=_worker_loop,
        args=(database,),
        daemon=True,
        name="omnix-rpg-world-generation",
    )
    thread.start()
    return True
