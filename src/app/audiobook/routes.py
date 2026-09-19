"""Browser API for canonical audiobook projects and durable source jobs."""
from __future__ import annotations

import asyncio
import logging
import threading
from functools import wraps
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.runtime import ensure_postgresql_runtime_ready

from .extraction import MAX_SOURCE_BYTES, UnsupportedSource
from .service import AudiobookService
from .render_service import run_render_once
from .assembly_service import run_assemble_once
from .export_service import run_export_once
from .worker import run_analyze_once, run_ingest_once


_LOG = logging.getLogger(__name__)
_ROUTE_SENTINEL = "_omnix_audiobook_project_routes_registered"
_HOOK_SENTINEL = "_omnix_audiobook_project_route_hook_installed"


class CreateAudiobookProject(BaseModel):
    title: str
    author: str = ""
    language: str = "en"


class CreateSpeaker(BaseModel):
    canonical_name: str


class AssignVoice(BaseModel):
    voice_profile_id: str


class ConfirmSpeakerAlias(BaseModel):
    alias: str


class ResolveReviewIssue(BaseModel):
    speaker_id: str
    role: str
    delivery: str = ""


class StartRender(BaseModel):
    provider_id: str = "faster-qwen3-tts"
    model_id: str = "Qwen3-TTS"
    model_revision: str
    generation_parameters: dict[str, object] = Field(default_factory=dict)
    seed: int | None = None


class StartExport(BaseModel):
    format: str = "m4b"


class SetPronunciation(BaseModel):
    source_term: str
    spoken_term: str


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

    @gateway.get("/api/audiobook/voices", tags=["audiobook"])
    def list_voices() -> dict[str, object]:
        return {"voices": AudiobookService.list_voices()}

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

    @gateway.post("/api/audiobook/projects/{project_id}/cover", tags=["audiobook"])
    async def upload_cover(project_id: str, request: Request,
                           filename: str = Query(default="cover")) -> dict[str, str]:
        if int(request.headers.get("content-length", "0") or 0) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="cover is too large")
        content = await request.body()
        service, context = await asyncio.to_thread(_service_and_context)
        try:
            return await asyncio.to_thread(service.set_cover, context,
                                           project_id=project_id, content=content,
                                           filename=filename)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/speakers", tags=["audiobook"])
    def add_speaker(project_id: str, request: CreateSpeaker) -> dict[str, str]:
        service, context = _service_and_context()
        try:
            return service.add_speaker(context, project_id=project_id, **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/pronunciations", tags=["audiobook"])
    def set_pronunciation(project_id: str, request: SetPronunciation) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.set_pronunciation(context, project_id=project_id,
                                             **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/speakers/{speaker_id}/casting", tags=["audiobook"])
    def assign_voice(project_id: str, speaker_id: str, request: AssignVoice) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.assign_voice(
                context, project_id=project_id, speaker_id=speaker_id,
                voice_profile_id=request.voice_profile_id,
            )
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="speaker not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/speakers/{speaker_id}/aliases", tags=["audiobook"])
    def confirm_alias(project_id: str, speaker_id: str, request: ConfirmSpeakerAlias) -> dict[str, str]:
        service, context = _service_and_context()
        try:
            return service.confirm_alias(context, project_id=project_id,
                                         speaker_id=speaker_id, alias=request.alias)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="speaker not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/review/{issue_id}", tags=["audiobook"])
    def resolve_issue(project_id: str, issue_id: str, request: ResolveReviewIssue) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.resolve_issue(
                context, project_id=project_id, issue_id=issue_id, **request.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="review issue or speaker not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/render", tags=["audiobook"], status_code=202)
    def start_render(project_id: str, request: StartRender) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.start_render(context, project_id=project_id, **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/exports", tags=["audiobook"], status_code=202)
    def start_export(project_id: str, request: StartExport) -> dict[str, str]:
        service, context = _service_and_context()
        try:
            return service.start_export(context, project_id=project_id, format=request.format)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.get("/api/audiobook/projects/{project_id}/exports", tags=["audiobook"])
    def list_exports(project_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        return {"exports": service.list_exports(context, project_id)}

    @gateway.get("/api/audiobook/projects/{project_id}/exports/{export_id}/download", tags=["audiobook"])
    def download_export(project_id: str, export_id: str) -> Response:
        service, context = _service_and_context()
        try:
            content, mime, format = service.read_export(
                context, project_id=project_id, export_id=export_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook export not found") from exc
        return Response(content, media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="audiobook.{format}"',
        })

    @gateway.get("/api/audiobook/projects/{project_id}/exports/{export_id}/report", tags=["audiobook"])
    def export_report(project_id: str, export_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.export_report(context, project_id=project_id,
                                         export_id=export_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook export not found") from exc

    stop = threading.Event()
    thread: threading.Thread | None = None
    render_thread: threading.Thread | None = None

    def worker_loop() -> None:
        worker_id = f"audiobook:ingest:{uuid4().hex}"
        while not stop.is_set():
            try:
                database = default_database()
                ensure_postgresql_runtime_ready(database)
                context = bootstrap_local_tenant(database)
                active = run_ingest_once(database, LocalBlobStore(), context, worker_id=worker_id)
                if not active:
                    active = run_analyze_once(database, context, worker_id=worker_id)
                if not active:
                    active = run_assemble_once(database, LocalBlobStore(), context, worker_id=worker_id)
                if not active:
                    active = run_export_once(database, LocalBlobStore(), context, worker_id=worker_id)
                if not active:
                    stop.wait(1.0)
            except Exception:
                _LOG.exception("Audiobook ingest worker could not poll")
                stop.wait(5.0)

    def start_worker() -> None:
        nonlocal thread, render_thread
        stop.clear()
        thread = threading.Thread(target=worker_loop, name="audiobook-ingest", daemon=True)
        thread.start()
        render_thread = threading.Thread(target=render_worker_loop, name="audiobook-render", daemon=True)
        render_thread.start()

    def render_worker_loop() -> None:
        worker_id = f"audiobook:render:{uuid4().hex}"
        while not stop.is_set():
            try:
                database = default_database()
                ensure_postgresql_runtime_ready(database)
                context = bootstrap_local_tenant(database)
                if not run_render_once(database, LocalBlobStore(), context, worker_id=worker_id):
                    stop.wait(1.0)
            except Exception:
                _LOG.exception("Audiobook render worker could not poll")
                stop.wait(5.0)

    def stop_worker() -> None:
        stop.set()
        if thread is not None:
            thread.join(timeout=2.0)
        if render_thread is not None:
            render_thread.join(timeout=2.0)

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
