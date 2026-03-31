"""
Job queue system for offloading heavy work (TTS generation) from Flask API.

Architecture: Client → Flask → Queue → Worker → Cache → Flask → Client

Flask endpoints enqueue jobs, background workers process them,
results are stored in cache, and clients poll for completion.
"""

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
    """Represents a TTS generation job."""
    def __init__(self, job_id: str, text: str, speaker: str = None,
                 voice_id: str = None, chunk_index: int = -1, **kwargs):
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
        self.completed_at = None


class JobQueue:
    """Thread-safe job queue with background worker for TTS processing.

    Usage:
        queue = JobQueue(worker_fn=my_tts_function)
        queue.start()

        job_id = queue.enqueue("Hello world", speaker="narrator")

        # Poll for result
        result = queue.get_result(job_id)
        if result and result['status'] == 'completed':
            audio = result['audio']
    """

    def __init__(self, worker_fn: Callable = None, max_workers: int = 1,
                 max_cache_size: int = 100, max_retries: int = 3):
        """
        Args:
            worker_fn: Function(text, speaker, voice_id, **kwargs) -> dict with audio result
            max_workers: Number of background worker threads
            max_cache_size: Max completed jobs to keep in cache
            max_retries: Max retry attempts for failed jobs
        """
        self._worker_fn = worker_fn
        self._max_workers = max_workers
        self._max_cache_size = max_cache_size
        self._max_retries = max_retries

        self._queue: list = []  # pending jobs
        self._jobs: OrderedDict = OrderedDict()  # all jobs by id
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._workers: list = []
        self._running = False

    def start(self) -> None:
        """Start background worker threads."""
        with self._lock:
            if self._running:
                return
            self._running = True

        for i in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, name=f"job-worker-{i}", daemon=True)
            self._workers.append(t)
            t.start()

        logger.info("JobQueue started with %d worker(s)", self._max_workers)

    def stop(self) -> None:
        """Stop all workers gracefully."""
        with self._condition:
            self._running = False
            self._condition.notify_all()

        for t in self._workers:
            t.join(timeout=5)

        self._workers.clear()
        logger.info("JobQueue stopped")

    def enqueue(self, text: str, speaker: str = None, voice_id: str = None,
                chunk_index: int = -1, **kwargs) -> str:
        """Add a job to the queue. Returns job_id."""
        job_id = uuid.uuid4().hex
        job = Job(job_id=job_id, text=text, speaker=speaker,
                  voice_id=voice_id, chunk_index=chunk_index, **kwargs)

        with self._condition:
            self._jobs[job_id] = job
            self._queue.append(job)
            self._condition.notify()

        logger.info("Enqueued job %s (queue depth: %d)", job_id, len(self._queue))
        return job_id

    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Poll for job result. Returns job status and result if available."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            return {
                "status": job.status,
                "job_id": job.job_id,
                "chunk_index": job.chunk_index,
                "audio": job.result if job.status == JobStatus.COMPLETED else None,
                "error": job.error if job.status == JobStatus.FAILED else None,
                "queue_position": self._queue.index(job) if job in self._queue else -1,
            }

    def get_queue_position(self, job_id: str) -> int:
        """Get position of job in queue (-1 if not in queue)."""
        with self._lock:
            for i, job in enumerate(self._queue):
                if job.job_id == job_id:
                    return i
            return -1

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.PENDING:
                return False

            self._queue = [j for j in self._queue if j.job_id != job_id]
            job.status = JobStatus.FAILED
            job.error = "Cancelled by user"
            job.completed_at = time.time()
            logger.info("Cancelled job %s", job_id)
            return True

    def _worker_loop(self) -> None:
        """Background worker that processes jobs from the queue."""
        while True:
            with self._condition:
                while self._running and not self._queue:
                    self._condition.wait()

                if not self._running:
                    return

                job = self._queue.pop(0)
                job.status = JobStatus.PROCESSING

            self._process_job(job)

    def _process_job(self, job: Job) -> None:
        """Process a single job using the worker function (with retry)."""
        if self._worker_fn is None:
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = "No worker function configured"
                job.completed_at = time.time()
            return

        last_err: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                result = self._worker_fn(
                    job.text, job.speaker, job.voice_id, **job.kwargs
                )

                with self._lock:
                    job.result = result
                    job.status = JobStatus.COMPLETED
                    job.completed_at = time.time()
                    self._cleanup_old_jobs()

                logger.info("Job %s completed (%.2fs)", job.job_id, job.completed_at - job.created_at)
                return

            except Exception as e:
                last_err = e
                logger.warning("Job %s attempt %d/%d failed: %s", job.job_id, attempt + 1, self._max_retries, e)

        # All retries exhausted
        with self._lock:
            job.status = JobStatus.FAILED
            job.error = str(last_err)
            job.completed_at = time.time()

        logger.error("Job %s failed after %d attempts: %s", job.job_id, self._max_retries, last_err)

    def get_ordered_results(self, job_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Return results for *job_ids* sorted by ``chunk_index``.

        This is used to reassemble chunks in order even when they completed
        out of order.
        """
        with self._lock:
            results = []
            for jid in job_ids:
                job = self._jobs.get(jid)
                if job is None:
                    results.append(None)
                    continue
                results.append({
                    "status": job.status,
                    "job_id": job.job_id,
                    "chunk_index": job.chunk_index,
                    "audio": job.result if job.status == JobStatus.COMPLETED else None,
                    "error": job.error if job.status == JobStatus.FAILED else None,
                })
            # Sort by chunk_index so callers can emit in order
            results.sort(key=lambda r: (r or {}).get("chunk_index", 0))
            return results

    def _cleanup_old_jobs(self) -> None:
        """Remove old completed jobs when cache is full.

        Must be called while holding self._lock.
        """
        completed = [
            jid for jid, j in self._jobs.items()
            if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        while len(completed) > self._max_cache_size:
            oldest_id = completed.pop(0)
            self._jobs.pop(oldest_id, None)

    @property
    def pending_count(self) -> int:
        """Number of jobs waiting to be processed."""
        with self._lock:
            return len(self._queue)

    @property
    def is_running(self) -> bool:
        """Whether workers are active."""
        return self._running


# Global job queue instance
_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """Get or create the global job queue."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue


def init_job_queue(worker_fn: Callable = None) -> JobQueue:
    """Initialize and start the global job queue."""
    global _job_queue
    _job_queue = JobQueue(worker_fn=worker_fn)
    _job_queue.start()
    return _job_queue
