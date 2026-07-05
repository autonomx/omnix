"""Memory-bounded Voice Studio job list route."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, Query

from app.jobs import JobListResponse, default_job_store

from .job_summaries import voice_job_projections

_ROUTE_SENTINEL = "_omnix_voice_job_summaries_registered"
_HOOK_SENTINEL = "_omnix_voice_job_summaries_hook_installed"
VOICE_JOB_SUMMARIES_PATH = "/api/jobs/voice-summaries"
VOICE_JOB_MODULES = {"voice", "voice-cloning"}
DEFAULT_VOICE_JOB_LIMIT = 40
MAX_VOICE_JOB_LIMIT = 100


def register_voice_job_summary_routes(gateway: FastAPI) -> None:
    """Register a bounded list projection for the Voice Studio browser view."""
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get(VOICE_JOB_SUMMARIES_PATH, response_model=JobListResponse, include_in_schema=False)
    async def voice_job_summaries(
        limit: int = Query(default=DEFAULT_VOICE_JOB_LIMIT, ge=1, le=MAX_VOICE_JOB_LIMIT),
    ) -> JobListResponse:
        jobs = [
            job
            for job in default_job_store().list_jobs()
            if job.module in VOICE_JOB_MODULES
        ][:limit]
        return JobListResponse(jobs=voice_job_projections(jobs))


def install_voice_job_summary_hook() -> None:
    """Install the Voice Studio summary route before gateway construction."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_voice_job_summary_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
