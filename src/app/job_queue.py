import logging
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class JobStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    def __init__(self, job_id: str, text: str, speaker: str = None, voice_id: str = None, chunk_index: int = -1, **kwargs):
        self.job_id = job_id
        self.text = text
        self.speaker = speaker
        self.voice_id = voice_id
        self.chunk_index = chunk_index
        self.kwargs = kwargs
        self.status = JobStatus.PENDING
        self.result = None
        self.error = None
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
        self.response_persisted_at = None

    def timestamps(self) -> Dict[str, Optional[int]]:
        return {
            "server_job_created_at": int(self.created_at * 1000),
            "server_job_started_at": int(self.started_at * 1000) if self.started_at is not None else None,
            "server_job_completed_at": int(self.completed_at * 1000) if self.completed_at is not None else None,
            "server_response_persisted_at": int(self.response_persisted_at * 1000) if self.response_persisted_at is not None else None,
        }


class JobQueue:
    def __init__(self, worker_fn: Callable = None, max_workers: int = 1, max_cache_size: int = 100, max_retries: int = 3):
        self._worker_fn = worker_fn
        self._max_workers = max_workers
        self._max_cache_size = max_cache_size
        self._max_retries = max_retries
        self._queue: list = []
        self._jobs: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._workers: list = []
        self._running = False

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        for i in range(self._max_workers):
            worker = threading.Thread(target=self._worker_loop, name=f"job-worker-{i}", daemon=True)
            self._workers.append(worker)
            worker.start()
        logger.info("JobQueue started with %d worker(s)", self._max_workers)

    def stop(self) -> None:
        with self._condition:
            self._running = False
            self._condition.notify_all()
        for worker in self._workers:
            worker.join(timeout=5)
        self._workers.clear()
        logger.info("JobQueue stopped")

    def enqueue(self, text: str, speaker: str = None, voice_id: str = None, chunk_index: int = -1, **kwargs) -> str:
        job_id = uuid.uuid4().hex
        job = Job(job_id, text, speaker, voice_id, chunk_index, **kwargs)
        with self._condition:
            self._jobs[job_id] = job
            self._queue.append(job)
            self._condition.notify()
        logger.info("Enqueued job %s (queue depth: %d)", job_id, len(self._queue))
        return job_id

    def _result_for(self, job: Job) -> Dict[str, Any]:
        return {
            "status": job.status,
            "job_id": job.job_id,
            "chunk_index": job.chunk_index,
            "audio": job.result if job.status == JobStatus.COMPLETED else None,
            "error": job.error if job.status == JobStatus.FAILED else None,
            "timestamps": job.timestamps(),
        }

    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            result = self._result_for(job)
            result["queue_position"] = self._queue.index(job) if job in self._queue else -1
            return result

    def get_queue_position(self, job_id: str) -> int:
        with self._lock:
            for index, job in enumerate(self._queue):
                if job.job_id == job_id:
                    return index
            return -1

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.PENDING:
                return False
            self._queue = [queued for queued in self._queue if queued.job_id != job_id]
            self._finish_job(job, JobStatus.FAILED, error="Cancelled by user")
            logger.info("Cancelled job %s", job_id)
            return True

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while self._running and not self._queue:
                    self._condition.wait()
                if not self._running:
                    return
                job = self._queue.pop(0)
                job.status = JobStatus.PROCESSING
                job.started_at = time.time()
            self._process_job(job)

    def _finish_job(self, job: Job, status: str, result: Any = None, error: str = None) -> None:
        job.status = status
        job.result = result
        job.error = error
        job.completed_at = time.time()
        job.response_persisted_at = job.completed_at

    def _process_job(self, job: Job) -> None:
        if self._worker_fn is None:
            with self._lock:
                self._finish_job(job, JobStatus.FAILED, error="No worker function configured")
            return
        last_error = None
        for attempt in range(self._max_retries):
            try:
                result = self._worker_fn(job.text, job.speaker, job.voice_id, **job.kwargs)
                with self._lock:
                    self._finish_job(job, JobStatus.COMPLETED, result=result)
                    self._cleanup_old_jobs()
                logger.info("Job %s completed (%.2fs)", job.job_id, job.completed_at - job.created_at)
                return
            except Exception as exc:
                last_error = exc
                logger.warning("Job %s attempt %d/%d failed: %s", job.job_id, attempt + 1, self._max_retries, exc)
        with self._lock:
            self._finish_job(job, JobStatus.FAILED, error=str(last_error))
        logger.error("Job %s failed after %d attempts: %s", job.job_id, self._max_retries, last_error)

    def get_ordered_results(self, job_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        with self._lock:
            results = [self._result_for(self._jobs[job_id]) if job_id in self._jobs else None for job_id in job_ids]
        results.sort(key=lambda result: (result or {}).get("chunk_index", 0))
        return results

    def _cleanup_old_jobs(self) -> None:
        completed = [job_id for job_id, job in self._jobs.items() if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)]
        while len(completed) > self._max_cache_size:
            self._jobs.pop(completed.pop(0), None)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_running(self) -> bool:
        return self._running


_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue


def init_job_queue(worker_fn: Callable = None) -> JobQueue:
    global _job_queue
    _job_queue = JobQueue(worker_fn=worker_fn)
    _job_queue.start()
    return _job_queue
