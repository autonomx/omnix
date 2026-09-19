"""Browser API for canonical audiobook projects and durable source jobs."""
from __future__ import annotations

import asyncio
import logging
import threading
from functools import wraps
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.runtime import ensure_postgresql_runtime_ready

from .extraction import MAX_SOURCE_BYTES, UnsupportedSource
from .service import AudiobookService
from .worker import run_ingest_once


_LOG = logging.getLogger(__name__)
_ROUTE_SENTINEL = "_omnix_audiobook_project_routes_registered"
_HOOK_SENTINEL = "_omnix_audiobook_project_route_hook_installed"


class CreateAudiobookProject(BaseModel):
    title: str
    author: str = ""
    language: str = "en"


def _service_and_context() -> tuple[AudiobookService, Any]:
    database = default_database()
    ensure_postgresql_runtime_ready(database)
    return AudiobookService(database, LocalBlobStore()), bootstrap_local_tenant(database)


def register_audiobook_routes(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get("/api/audiobook/projects", tags=["audiobook"])
    def list_projects() -> dict[str, object]:
        service, context = _service_and_context()
        return {"projects": service.list_projects(context)}

    @gateway.post("/api/audiobook/projects", tags=["audiobook"])
    def create_project(request: CreateAudiobookProject) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.create_project(context, **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.get("/api/audiobook/projects/{project_id}", tags=["audiobook"])
    def get_project(project_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.get_project(context, project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/source", tags=["audiobook"], status_code=202)
    async def upload_source(
        project_id: str, request: Request,
        source_format: str = Query(pattern="^(epub|txt|md)$"),
        filename: str = Query(default="book"),
    ) -> dict[str, str]:
        if int(request.headers.get("content-length", "0") or 0) > MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="source is too large")
        content = await request.body()
        if len(content) > MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="source is too large")
        service, context = await asyncio.to_thread(_service_and_context)
        try:
            return await asyncio.to_thread(
                service.submit_source, context, project_id=project_id,
                source_format=source_format, content=content, filename=filename,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        except UnsupportedSource as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    stop = threading.Event()
    thread: threading.Thread | None = None

    def worker_loop() -> None:
        worker_id = f"audiobook:ingest:{uuid4().hex}"
        while not stop.is_set():
            try:
                database = default_database()
                ensure_postgresql_runtime_ready(database)
                context = bootstrap_local_tenant(database)
                active = run_ingest_once(database, LocalBlobStore(), context, worker_id=worker_id)
                if not active:
                    stop.wait(1.0)
            except Exception:
                _LOG.exception("Audiobook ingest worker could not poll")
                stop.wait(5.0)

    def start_worker() -> None:
        nonlocal thread
        stop.clear()
        thread = threading.Thread(target=worker_loop, name="audiobook-ingest", daemon=True)
        thread.start()

    def stop_worker() -> None:
        stop.set()
        if thread is not None:
            thread.join(timeout=2.0)

    gateway.router.add_event_handler("startup", start_worker)
    gateway.router.add_event_handler("shutdown", stop_worker)


def install_audiobook_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_audiobook_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
