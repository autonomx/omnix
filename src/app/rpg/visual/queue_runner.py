"""Compatibility wrapper for global queue runner."""
from __future__ import annotations

from app.image.queue_runner import run_one_image_job


def run_one_queued_job(*, lease_seconds: int = 300):
    # Current global runner does not yet consume lease_seconds explicitly.
    return run_one_image_job()


__all__ = ["run_one_image_job", "run_one_queued_job"]
