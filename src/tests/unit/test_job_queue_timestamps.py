import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from app.job_queue import JobQueue, JobStatus


def test_job_queue_exposes_server_timestamps_after_completion():
    queue = JobQueue(worker_fn=lambda text, speaker, voice_id, **kwargs: {"ok": True}, max_workers=1)
    queue.start()
    try:
        job_id = queue.enqueue("hello")
        deadline = time.time() + 2
        result = None
        while time.time() < deadline:
            result = queue.get_result(job_id)
            if result and result["status"] == JobStatus.COMPLETED:
                break
            time.sleep(0.01)

        assert result is not None
        assert result["status"] == JobStatus.COMPLETED
        timestamps = result["timestamps"]
        assert timestamps["server_job_created_at"] is not None
        assert timestamps["server_job_started_at"] is not None
        assert timestamps["server_job_completed_at"] is not None
        assert timestamps["server_response_persisted_at"] is not None
        assert timestamps["server_job_created_at"] <= timestamps["server_job_started_at"] <= timestamps["server_job_completed_at"]
        assert timestamps["server_response_persisted_at"] >= timestamps["server_job_completed_at"]
    finally:
        queue.stop()


def test_job_queue_exposes_pending_timestamps_before_worker_start():
    queue = JobQueue(worker_fn=lambda text, speaker, voice_id, **kwargs: {"ok": True}, max_workers=1)
    job_id = queue.enqueue("hello")

    result = queue.get_result(job_id)

    assert result is not None
    assert result["status"] == JobStatus.PENDING
    timestamps = result["timestamps"]
    assert timestamps["server_job_created_at"] is not None
    assert timestamps["server_job_started_at"] is None
    assert timestamps["server_job_completed_at"] is None
    assert timestamps["server_response_persisted_at"] is None
