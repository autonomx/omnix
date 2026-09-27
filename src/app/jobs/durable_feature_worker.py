"""Lease-backed execution for legacy feature jobs still using the shared Job API.

The HTTP/API process only enqueues these jobs. A worker-role gateway owns this
poller through GatewayBackgroundRuntime, claims PostgreSQL leases, renews them
while provider work runs, and fences durable mutations if singleton background
authority is lost.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from app.gateway.background_runtime import (
    BackgroundOwnershipUnavailable,
    BackgroundWorker,
    register_background_worker,
)
from app.jobs.models import CompleteJobRequest, FailJobRequest, JobRecord, JobStatus, ResourceClass
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.unit_of_work import unit_of_work

logger = logging.getLogger(__name__)

DURABLE_FEATURE_JOB_TYPES = frozenset(
    {
        "story.generate",
        "podcast.generate",
        "rpg.turn",
        "rpg.report.last10",
        "tts.synthesize",
        "tts.multi_speaker_synthesize",
        "voice-cloning.create-profile",
        "voice-cloning.transcribe-sample",
        "image.generate",
        "assistant.deep_research",
    }
)
_DURABLE_RESOURCE_CLASSES = tuple(resource.value for resource in ResourceClass)


class _AuthorityBoundJobStore:
    """Require live singleton authority before durable executor mutations."""

    _MUTATING = frozenset(
        {
            "mark_running",
            "update_progress",
            "update_job_input",
            "update_job_stages",
            "complete_job",
            "fail_job",
            "finalize_cancel",
            "append_log",
        }
    )

    def __init__(self, store: Any, authority: Any, job: JobRecord) -> None:
        self._store = store
        self._authority = authority
        self._job_id = job.id
        self._lease_token = job.lease.token if job.lease is not None else None
        self._worker_id = job.lease.worker_id if job.lease is not None else None

    def require_execution_authority(self, job_id: str | None = None) -> None:
        target = job_id or self._job_id
        if target != self._job_id:
            raise JobClaimConflict("Durable feature executor cannot mutate another job")
        self._authority.require_live()
        with unit_of_work(self._store.database) as work:
            row = work.connection.execute(
                """
                SELECT 1
                  FROM omnix_jobs
                 WHERE id = %s AND workspace_id = %s
                   AND status IN ('leased', 'running')
                   AND lease_owner = %s AND lease_token = %s
                   AND lease_expires_at > clock_timestamp()
                """,
                (
                    self._job_id,
                    self._store.context.workspace_id,
                    self._worker_id,
                    self._lease_token,
                ),
            ).fetchone()
            work.rollback()
        if row is None:
            raise JobClaimConflict(f"Durable feature execution lease lost: {self._job_id}")

    def complete_job(self, job_id: str, request: CompleteJobRequest) -> JobRecord | None:
        self.require_execution_authority(job_id)
        return self._store.complete_job(job_id, request.model_copy(update={
            "worker_id": self._worker_id, "lease_token": self._lease_token,
        }))

    def fail_job(self, job_id: str, request: FailJobRequest) -> JobRecord | None:
        self.require_execution_authority(job_id)
        return self._store.fail_job(job_id, request.model_copy(update={
            "worker_id": self._worker_id, "lease_token": self._lease_token,
        }))

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._store, name)
        if name not in self._MUTATING or not callable(value):
            return value

        def guarded(*args: Any, **kwargs: Any) -> Any:
            self.require_execution_authority()
            return value(*args, **kwargs)

        return guarded


class DurableFeatureJobWorker:
    lease_seconds = 30
    renewal_seconds = 10

    def __init__(
        self,
        store: Any,
        authority: Any,
        *,
        poll_seconds: float = 0.25,
        max_concurrency: int = 4,
    ) -> None:
        self.store = store
        self.authority = authority
        self.poll_seconds = max(0.05, float(poll_seconds))
        self.max_concurrency = max(1, min(int(max_concurrency), 16))
        self.worker_id = f"gateway-feature:{uuid.uuid4().hex}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_lock = threading.Lock()
        self._active: dict[str, threading.Thread] = {}
        self.claim_count = 0
        self.completed_count = 0
        self.failure_count = 0
        self.last_error: str | None = None
        self.active_job_id: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self.authority.require_live()
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="omnix-durable-feature-jobs",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)
        with self._active_lock:
            active = list(self._active.values())
        for execution in active:
            # Provider calls are not forcibly interrupted. Threads are daemon
            # scoped and all later publications are authority/lease fenced once
            # the gateway releases singleton ownership.
            execution.join(timeout=1.0)

    @property
    def active_job_ids(self) -> tuple[str, ...]:
        with self._active_lock:
            return tuple(sorted(self._active))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "worker_id": self.worker_id,
            "max_concurrency": self.max_concurrency,
            "active_job_id": self.active_job_id,
            "active_job_ids": list(self.active_job_ids),
            "claim_count": self.claim_count,
            "completed_count": self.completed_count,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
        }

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.authority.require_live()
                self._reap_finished()
                with self._active_lock:
                    saturated = len(self._active) >= self.max_concurrency
                if saturated:
                    self._stop.wait(self.poll_seconds)
                    continue
                job = self._claim_one()
                if job is None:
                    self._stop.wait(self.poll_seconds)
                    continue
                self._launch_claimed(job)
            except BackgroundOwnershipUnavailable:
                return
            except Exception as exc:
                self.failure_count += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Durable feature worker iteration failed")
                self._stop.wait(min(2.0, self.poll_seconds * 4))

    def _launch_claimed(self, job: JobRecord) -> None:
        execution = threading.Thread(
            target=self._run_claimed,
            args=(job,),
            name=f"omnix-feature-job-{job.id[-8:]}",
            daemon=True,
        )
        with self._active_lock:
            self._active[job.id] = execution
            self.active_job_id = job.id
        execution.start()

    def _run_claimed(self, job: JobRecord) -> None:
        try:
            self._execute_claimed(job)
        finally:
            with self._active_lock:
                self._active.pop(job.id, None)
                self.active_job_id = next(iter(self._active), None)

    def _reap_finished(self) -> None:
        with self._active_lock:
            finished = [
                (job_id, execution)
                for job_id, execution in self._active.items()
                if not execution.is_alive()
            ]
            for job_id, _ in finished:
                self._active.pop(job_id, None)
            self.active_job_id = next(iter(self._active), None)

    def _claim_one(self) -> JobRecord | None:
        with unit_of_work(self.store.database) as work:
            record = work.jobs.claim_next(
                self.store.context,
                worker_id=self.worker_id,
                resource_classes=list(_DURABLE_RESOURCE_CLASSES),
                job_types=sorted(DURABLE_FEATURE_JOB_TYPES),
                lease_seconds=self.lease_seconds,
            )
            if record is None:
                work.rollback()
                return None
            record = work.jobs.mark_running(
                self.store.context,
                job_id=record["id"],
                worker_id=self.worker_id,
                lease_token=record["lease_token"],
            )
            work.commit()
        self.claim_count += 1
        return self.store._record(record)

    def _execute_claimed(self, job: JobRecord) -> None:
        lease = job.lease
        if lease is None:
            raise RuntimeError(f"Claimed job has no lease: {job.id}")
        token = lease.token
        renewal_stop = threading.Event()
        renewal = threading.Thread(
            target=self._renew_loop,
            args=(job.id, token, renewal_stop),
            name=f"omnix-feature-lease-{job.id[-8:]}",
            daemon=True,
        )
        renewal.start()
        try:
            authority_store = _AuthorityBoundJobStore(self.store, self.authority, job)
            result = execute_durable_feature_job(authority_store, job)
            if result.status in {
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELED,
                JobStatus.STALE,
            }:
                self.completed_count += 1
            self.last_error = None
        except (BackgroundOwnershipUnavailable, JobClaimConflict):
            # Ownership/lease loss is intentionally not converted into a second
            # write. Expiry/reclaim decides the durable outcome.
            return
        except Exception as exc:
            self.failure_count += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._record_unexpected_failure(job, exc)
        finally:
            renewal_stop.set()
            renewal.join(timeout=1.0)

    def _renew_loop(self, job_id: str, lease_token: str, stop: threading.Event) -> None:
        while not stop.wait(self.renewal_seconds):
            try:
                self.authority.require_live()
                with unit_of_work(self.store.database) as work:
                    work.jobs.renew_lease(
                        self.store.context,
                        job_id=job_id,
                        worker_id=self.worker_id,
                        lease_token=lease_token,
                        lease_seconds=self.lease_seconds,
                    )
                    work.commit()
            except Exception:
                return

    def _record_unexpected_failure(self, job: JobRecord, exc: Exception) -> None:
        lease = job.lease
        if lease is None:
            return
        try:
            self.authority.require_live()
            with unit_of_work(self.store.database) as work:
                work.jobs.fail(
                    self.store.context,
                    job_id=job.id,
                    worker_id=lease.worker_id,
                    lease_token=lease.token,
                    error={
                        "code": "durable_feature_execution_failed",
                        "message": type(exc).__name__,
                        "retryable": True,
                        "details": {"job_type": job.type},
                    },
                )
                work.commit()
        except JobClaimConflict:
            # A later claim owns the job. The stale executor must not mutate it.
            return
        except Exception:
            # Lease expiry/recovery remains authoritative if this write cannot
            # be proven to belong to the current worker.
            logger.exception("Could not persist durable feature worker failure: %s", job.id)


def execute_durable_feature_job(job_store: Any, job: JobRecord) -> JobRecord:
    """Dispatch an already-leased job without installing class monkey patches."""

    if job.type in {"story.generate", "podcast.generate", "rpg.turn", "rpg.report.last10"}:
        from app.jobs.inline_feature_jobs import execute_inline_feature_job

        return execute_inline_feature_job(job_store, job)
    if job.type in {
        "tts.synthesize",
        "tts.multi_speaker_synthesize",
        "voice-cloning.create-profile",
        "voice-cloning.transcribe-sample",
    }:
        from app.jobs.voice_inline import execute_voice_studio_job

        return execute_voice_studio_job(job_store, job)
    if job.type == "image.generate":
        from app.jobs.image_inline import execute_image_job

        return execute_image_job(job_store, job)
    if job.type == "assistant.deep_research":
        from app.jobs.research_inline import execute_research_job

        return execute_research_job(job_store, job)
    raise RuntimeError(f"Unsupported durable feature job type: {job.type}")


def register_durable_feature_job_worker(gateway: Any, store: Any) -> DurableFeatureJobWorker:
    runtime = getattr(gateway.state, "background_runtime", None)
    if runtime is None:
        raise RuntimeError("Durable feature worker requires composed background runtime")
    worker = DurableFeatureJobWorker(store, runtime)
    register_background_worker(
        gateway,
        BackgroundWorker(
            name="durable-feature-jobs",
            monitor=worker,
            startup=(worker.start,),
            shutdown=(worker.stop,),
        ),
    )
    gateway.state.durable_feature_job_worker = worker
    return worker


__all__ = [
    "DURABLE_FEATURE_JOB_TYPES",
    "DurableFeatureJobWorker",
    "execute_durable_feature_job",
    "register_durable_feature_job_worker",
]
