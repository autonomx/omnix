"""Durable asynchronous Campaign Genesis orchestration.

The HTTP path creates and saves a deterministic blocked campaign shell, then records
one PostgreSQL job. A lease-backed worker performs World Forge generation outside the
request, commits certified canon, materializes the session, and opens the first-turn
gate. Expired leases are reclaimed by the shared job repository after restart.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Mapping

from .contract import CampaignGenesisContract
from .materialization import materialize_world_forge_into_session, persist_campaign_genesis
from .world_forge_commit import require_world_forge_commit_ready
from .world_forge_generation import WorldForgeTopicGenerator
from .world_forge_pipeline import run_campaign_world_forge

CAMPAIGN_GENESIS_JOB_TYPE = "rpg.campaign_genesis.generate"
CAMPAIGN_GENESIS_RESOURCE_CLASS = "rpg_campaign_genesis"
CAMPAIGN_GENESIS_ASYNC_CONTRACT = "rpg_campaign_genesis_async_v1"
_DEFAULT_LEASE_SECONDS = 3600

_worker_lock = threading.Lock()
_worker_active = False


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def campaign_genesis_async_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Use asynchronous Genesis in production while keeping deterministic CI explicit."""

    env = environ or os.environ
    configured = str(env.get("OMNIX_RPG_CAMPAIGN_GENESIS_MODE") or "").strip().casefold()
    if configured:
        return configured not in {"sync", "synchronous", "disabled", "off", "test"}
    return str(env.get("RPG_TEST_MODE") or "").strip().casefold() != "deterministic"


def campaign_genesis_job_id(campaign_id: str) -> str:
    return f"rpg-genesis:{campaign_id}"


def _progress(
    *,
    status: str,
    stage: str,
    percent: int,
    job_id: str,
    error: str = "",
) -> dict[str, Any]:
    return {
        "contract_version": CAMPAIGN_GENESIS_ASYNC_CONTRACT,
        "job_id": job_id,
        "status": status,
        "stage": stage,
        "percent": max(0, min(int(percent), 100)),
        "launch_ready": status == "ready",
        "error": error,
    }


def _write_session_progress(
    campaign_id: str,
    *,
    status: str,
    stage: str,
    percent: int,
    job_id: str,
    error: str = "",
) -> dict[str, Any] | None:
    from app.rpg.session.service import load_session, save_session

    session = load_session(campaign_id)
    if not session:
        return None
    runtime = _mapping(session.get("runtime_state"))
    manifest = _mapping(session.get("manifest"))
    snapshot = _progress(
        status=status,
        stage=stage,
        percent=percent,
        job_id=job_id,
        error=error,
    )
    runtime["campaign_generation"] = snapshot
    runtime["active_job_id"] = None if status in {"ready", "failed"} else job_id
    runtime["last_error"] = error or None
    runtime["campaign_launch_gate"] = {
        "ready": status == "ready",
        "required_before_first_turn": True,
        "missing_requirements": (
            [] if status == "ready" else [f"campaign_genesis_{stage}"]
        ),
    }
    manifest["campaign_generation_status"] = status
    manifest["creation_status"] = "completed" if status == "ready" else status
    session["runtime_state"] = runtime
    session["manifest"] = manifest
    return save_session(session, compact=True)


def _database(value: Any | None) -> Any:
    if value is not None:
        return value
    from app.persistence.database import default_database

    return default_database()


def enqueue_campaign_genesis(
    result: dict[str, Any],
    *,
    contract: CampaignGenesisContract,
    compiled: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
    legacy: Mapping[str, Any],
    database: Any | None = None,
    kick_worker: bool = True,
) -> dict[str, Any]:
    """Persist a blocked shell and one durable World Forge job, then return immediately."""

    session = result.get("session") if isinstance(result.get("session"), dict) else None
    campaign_id = str(result.get("session_id") or "")
    if session is None or not campaign_id:
        return {
            **result,
            "ok": False,
            "status": "failed",
            "error": "campaign_genesis_session_missing",
        }
    if not contract.world_forge.enabled:
        return result

    job_id = campaign_genesis_job_id(campaign_id)
    runtime = _mapping(session.get("runtime_state"))
    setup = _mapping(session.get("setup_payload"))
    manifest = _mapping(session.get("manifest"))
    queued = _progress(
        status="queued",
        stage="queued",
        percent=0,
        job_id=job_id,
    )
    runtime["campaign_generation"] = queued
    runtime["active_job_id"] = job_id
    runtime["campaign_launch_gate"] = {
        "ready": False,
        "required_before_first_turn": True,
        "missing_requirements": ["campaign_genesis_queued"],
    }
    setup["world_forge"] = {
        "depth": contract.world_forge.depth,
        "topic_graph": dict(
            _mapping(compiled.get("compiled_world_forge")).get("topic_graph") or {}
        ),
        "async_job_id": job_id,
        "status": "queued",
    }
    manifest["campaign_generation_status"] = "queued"
    manifest["creation_job_id"] = job_id
    manifest["creation_status"] = "queued"
    session["runtime_state"] = runtime
    session["setup_payload"] = setup
    session["manifest"] = manifest

    from app.rpg.session.service import save_session

    saved = save_session(session, compact=True)
    db = _database(database)
    try:
        from app.persistence.identity_service import bootstrap_local_tenant
        from app.persistence.unit_of_work import unit_of_work

        context = bootstrap_local_tenant(db)
        with unit_of_work(db) as work:
            campaign = work.rpg.get_campaign(context, campaign_id, for_update=True)
            state = _mapping(saved.get("state"))
            if campaign is None:
                work.rpg.create_campaign(
                    context,
                    campaign_id=campaign_id,
                    title=str(state.get("title") or campaign_id),
                    state=state,
                    engine_version="rne-campaign-genesis-async-v1",
                    schema_version=str(manifest.get("schema_version") or "rpg-session-v1"),
                    seed=str(contract.world_options.seed or 0),
                    metadata={
                        "campaign_template": contract.campaign_template,
                        "world_forge_depth": contract.world_forge.depth,
                        "campaign_genesis_async": True,
                    },
                )
            existing = work.jobs.get_job(context, job_id)
            work.campaign_genesis.start(
                context,
                genesis_run_id=f"genesis:{campaign_id}:1",
                campaign_id=campaign_id,
                depth=contract.world_forge.depth,
                topic_graph=setup["world_forge"]["topic_graph"],
                progress=queued,
            )
            job = existing or work.jobs.create_job(
                context,
                {
                    "id": job_id,
                    "module": "rpg",
                    "job_type": CAMPAIGN_GENESIS_JOB_TYPE,
                    "resource_class": CAMPAIGN_GENESIS_RESOURCE_CLASS,
                    "priority": 20,
                    "max_attempts": 3,
                    "input_payload": {
                        "campaign_id": campaign_id,
                        "contract": contract.model_dump(mode="json"),
                        "compiled": dict(compiled),
                        "bootstrap": dict(bootstrap),
                        "legacy": dict(legacy),
                    },
                    "metadata": {
                        "contract_version": CAMPAIGN_GENESIS_ASYNC_CONTRACT,
                        "campaign_id": campaign_id,
                        "world_forge_depth": contract.world_forge.depth,
                    },
                },
            )
            work.commit()
    except Exception as exc:
        failed = _write_session_progress(
            campaign_id,
            status="failed",
            stage="enqueue_failed",
            percent=0,
            job_id=job_id,
            error=str(exc),
        )
        return {
            **result,
            "ok": False,
            "status": "failed",
            "session": failed or saved,
            "error": "campaign_genesis_enqueue_failed",
            "detail": str(exc),
            "creation_job": queued,
            "creation_progress": queued,
        }

    response = {
        **result,
        "ok": True,
        "status": "generating_world",
        "session": saved,
        "game": saved.get("state", {}),
        "creation_job": {**queued, "id": job["id"], "type": job["job_type"]},
        "creation_progress": queued,
    }
    if kick_worker:
        kick_campaign_genesis_worker(database=db)
    return response


def run_campaign_genesis_worker_once(
    *,
    worker_id: str = "rpg-genesis:local",
    database: Any | None = None,
    generator: WorldForgeTopicGenerator | None = None,
) -> dict[str, Any] | None:
    """Claim and execute one durable Genesis job. Returns ``None`` when idle."""

    db = _database(database)
    from app.persistence.identity_service import bootstrap_local_tenant
    from app.persistence.unit_of_work import unit_of_work

    context = bootstrap_local_tenant(db)
    with unit_of_work(db) as work:
        job = work.jobs.claim_next(
            context,
            worker_id=worker_id,
            resource_classes=[CAMPAIGN_GENESIS_RESOURCE_CLASS],
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
        payload = _mapping(job.get("input_payload"))
        campaign_id = str(payload.get("campaign_id") or "")
        work.campaign_genesis.update(
            context,
            campaign_id=campaign_id,
            status="running",
            progress=_progress(
                status="running",
                stage="world_forge",
                percent=10,
                job_id=job["id"],
            ),
            error={},
        )
        work.commit()

    _write_session_progress(
        campaign_id,
        status="running",
        stage="world_forge",
        percent=10,
        job_id=job["id"],
    )
    try:
        contract = CampaignGenesisContract.model_validate(payload.get("contract") or {})
        world_forge = run_campaign_world_forge(
            contract,
            campaign_id=campaign_id,
            compiled_genesis=_mapping(payload.get("compiled")),
            generator=generator,
        )
        certification = require_world_forge_commit_ready(world_forge)
        from app.rpg.session.service import load_session, save_session

        session = load_session(campaign_id)
        if not session:
            raise RuntimeError(f"campaign shell is missing: {campaign_id}")
        materialized = materialize_world_forge_into_session(session, contract, world_forge)
        persistence = persist_campaign_genesis(
            materialized,
            contract,
            world_forge,
            database=db,
            required=True,
            genesis_run_started=True,
        )
        saved = save_session(materialized, compact=True)
        with unit_of_work(db) as work:
            completed = work.jobs.complete(
                context,
                job_id=job["id"],
                worker_id=worker_id,
                lease_token=str(job["lease_token"]),
                output_refs=[
                    {
                        "campaign_id": campaign_id,
                        "campaign_bible_content_hash": certification.content_hash,
                    }
                ],
                progress=_progress(
                    status="ready",
                    stage="launch_ready",
                    percent=100,
                    job_id=job["id"],
                ),
            )
            work.commit()
        return {
            "ok": True,
            "status": "ready",
            "campaign_id": campaign_id,
            "job": completed,
            "session": saved,
            "persistence": persistence,
            "commit_certification": certification.as_dict(),
        }
    except Exception as exc:
        with unit_of_work(db) as work:
            failed = work.jobs.fail(
                context,
                job_id=job["id"],
                worker_id=worker_id,
                lease_token=str(job["lease_token"]),
                error={"code": "campaign_genesis_failed", "message": str(exc)},
                retry_delay_seconds=1,
            )
            retrying = failed["status"] == "retrying"
            work.campaign_genesis.update(
                context,
                campaign_id=campaign_id,
                status="retrying" if retrying else "failed",
                progress=_progress(
                    status="retrying" if retrying else "failed",
                    stage="retry_wait" if retrying else "failed",
                    percent=10,
                    job_id=job["id"],
                    error=str(exc),
                ),
                error={"code": "campaign_genesis_failed", "message": str(exc)},
            )
            work.commit()
        _write_session_progress(
            campaign_id,
            status="retrying" if retrying else "failed",
            stage="retry_wait" if retrying else "failed",
            percent=10,
            job_id=job["id"],
            error=str(exc),
        )
        return {
            "ok": False,
            "status": failed["status"],
            "campaign_id": campaign_id,
            "job": failed,
            "error": "campaign_genesis_failed",
            "detail": str(exc),
        }


def _worker_loop(database: Any | None) -> None:
    global _worker_active
    try:
        while run_campaign_genesis_worker_once(database=database) is not None:
            pass
    finally:
        with _worker_lock:
            _worker_active = False


def kick_campaign_genesis_worker(*, database: Any | None = None) -> bool:
    """Start one process-local recovery worker without creating duplicate consumers."""

    global _worker_active
    if not campaign_genesis_async_enabled():
        return False
    with _worker_lock:
        if _worker_active:
            return False
        _worker_active = True
    thread = threading.Thread(
        target=_worker_loop,
        args=(database,),
        name="omnix-rpg-campaign-genesis",
        daemon=True,
    )
    thread.start()
    return True
