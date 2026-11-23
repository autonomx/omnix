"""Synthetic ``platform.probe`` job for canaries and deployment tests.

It does bounded, side-effect-free work (a cancellable wait) and returns a
receipt, so rolling-upgrade and topology tests can prove each job ran exactly
once without loading models or calling providers.
"""
from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field

from .handlers import JobHandlerSpec, JobResult, JobRun
from .models import ResourceClass

PLATFORM_PROBE_JOB_TYPE = "platform.probe"


class PlatformProbeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_ms: int = Field(default=100, ge=0, le=5_000)
    label: str = Field(default="probe", min_length=1, max_length=64)


def _run_probe(run: JobRun[PlatformProbeInput]) -> JobResult:
    payload = run.input
    deadline = time.monotonic() + payload.duration_ms / 1000
    while time.monotonic() < deadline:
        if run.cancelled():
            raise RuntimeError("platform probe cancelled")
        time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
    return JobResult(output_refs=({"kind": "platform_probe", "label": payload.label, "duration_ms": payload.duration_ms},))


PLATFORM_PROBE_JOB = JobHandlerSpec(
    type=PLATFORM_PROBE_JOB_TYPE,
    run=_run_probe,
    failure_code="platform_probe_failed",
    input_model=PlatformProbeInput,
    resource_class=ResourceClass.CPU,
    timeout_seconds=30,
    max_attempts=3,
)

__all__ = ["PLATFORM_PROBE_JOB", "PLATFORM_PROBE_JOB_TYPE", "PlatformProbeInput"]
