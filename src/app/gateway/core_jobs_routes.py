"""Core jobs routes with explicitly injected store factories."""

from __future__ import annotations

import logging

from .internal_jobs_routes import register_internal_jobs_routes

from .core_services import (
    CancelJobRequest,
    CreateJobRequest,
    HTTPException,
    Header,
    JobListResponse,
    JobRecord,
    Query,
    StreamingResponse,
    _live_job_event_stream,
    _parse_event_id,
    _sse_event,
    asyncio,
    cancel_chat_generation_job,
    summarize_job,
)


def register_core_jobs_routes(gateway, *, get_chat_store, get_job_store):
    register_internal_jobs_routes(gateway, get_job_store=get_job_store)
    @gateway.post("/api/jobs", response_model=JobRecord, tags=["jobs"])
    def create_job(request: CreateJobRequest) -> JobRecord:
        if request.type in {"chat.generate", "rpg.turn.foreground_record"} or (
            {"record_only", "inline_execution", "execution_owner", "foreground_record", "direct_foreground_route"}
            & request.compat.keys()
        ):
            raise HTTPException(status_code=422, detail="job_execution_authority_is_server_owned")
        registry = getattr(gateway.state, "job_handler_registry", None)
        if registry is not None and registry.get(request.type) is not None:
            request = registry.validate_submission(request)
        return get_job_store().create_job(request)

    @gateway.get("/api/jobs", response_model=JobListResponse, tags=["jobs"])
    def list_jobs(
        limit: int = Query(default=100, ge=1, le=500), full: bool = False
    ) -> JobListResponse:
        jobs = get_job_store().list_jobs(limit=limit)
        if full:
            return JobListResponse(jobs=jobs)
        return JobListResponse(jobs=[summarize_job(job) for job in jobs])

    @gateway.get("/events", include_in_schema=False)
    async def events(
        after_id: int = 0,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        return StreamingResponse(
            _live_job_event_stream(
                await asyncio.to_thread(get_job_store),
                after_id=_parse_event_id(last_event_id, fallback=after_id),
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @gateway.get("/api/jobs/events", tags=["jobs"])
    def job_events(after_id: int = 0, limit: int = 100) -> StreamingResponse:
        events = get_job_store().list_events(after_id=after_id, limit=limit)

        def generate():
            for event in events:
                yield _sse_event(
                    event.event_type, event.model_dump(mode="json"), event_id=event.id
                )

        return StreamingResponse(generate(), media_type="text/event-stream")

    @gateway.get("/api/jobs/{job_id}", response_model=JobRecord, tags=["jobs"])
    def get_job(job_id: str) -> JobRecord:
        job = get_job_store().get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job

    @gateway.post("/api/jobs/claim", tags=["jobs"], deprecated=True)
    @gateway.post("/api/jobs/{job_id}/complete", tags=["jobs"], deprecated=True)
    @gateway.post("/api/jobs/{job_id}/fail", tags=["jobs"], deprecated=True)
    def retired_worker_protocol(job_id: str | None = None):
        logging.getLogger(__name__).warning("Retired public job worker endpoint requested")
        raise HTTPException(status_code=410, detail="worker_protocol_moved_to_internal_jobs")

    @gateway.post("/api/jobs/{job_id}/cancel", response_model=JobRecord, tags=["jobs"])
    def cancel_job(job_id: str, request: CancelJobRequest) -> JobRecord:
        job_store = get_job_store()
        current = job_store.get_job(job_id)
        if current is not None and current.type == "chat.generate":
            job = cancel_chat_generation_job(
                get_chat_store(),
                job_store,
                job_id,
                request,
            )
        else:
            job = job_store.cancel_job(job_id, request)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job
