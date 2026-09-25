"""Browser API for canonical audiobook projects and durable source jobs."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.runtime import ensure_postgresql_runtime_ready
from app.runtime_paths import resources_data_root

from .extraction import (
    SUPPORTED_SOURCE_FORMATS,
    normalize_extraction_settings,
    parse_page_ranges,
)

if TYPE_CHECKING:
    from .service import AudiobookService


_LOG = logging.getLogger(__name__)
_ROUTE_SENTINEL = "_omnix_audiobook_project_routes_registered"
_HOOK_SENTINEL = "_omnix_audiobook_project_route_hook_installed"
_SOURCE_FORMAT_PATTERN = "^(" + "|".join(sorted(SUPPORTED_SOURCE_FORMATS)) + ")$"
_SOURCE_LIBRARY_DISPLAY_PATH = Path("resources") / "data" / "audiobooks"
_SERVICE_CONTEXT_LOCK = threading.Lock()
_SERVICE_CONTEXT: tuple[Any, Any] | None = None


def _source_library_root() -> Path:
    root = resources_data_root() / "audiobooks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _source_library_files() -> dict[str, object]:
    root = _source_library_root().resolve()
    files: list[dict[str, object]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower().lstrip(".") not in SUPPORTED_SOURCE_FORMATS:
            continue
        try:
            stat = path.stat()
            name = path.relative_to(root).as_posix()
        except OSError:
            continue
        files.append({
            "name": name,
            "source_format": path.suffix.lower().lstrip("."),
            "size_bytes": stat.st_size,
        })
    files.sort(key=lambda item: str(item["name"]).casefold())
    return {"directory": str(_SOURCE_LIBRARY_DISPLAY_PATH), "files": files}


def _resolve_source_library_file(filename: str) -> Path:
    root = _source_library_root().resolve()
    candidate = (root / Path(filename)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("source library path is outside the audiobook directory") from exc
    if not candidate.is_file():
        raise FileNotFoundError(filename)
    if candidate.suffix.lower().lstrip(".") not in SUPPORTED_SOURCE_FORMATS:
        raise ValueError("unsupported source format")
    return candidate


def _page_extraction_settings(source_format: str, exclude_pages: str | None) -> dict[str, object]:
    if not exclude_pages or not exclude_pages.strip():
        return {}
    return normalize_extraction_settings(
        source_format, {"excluded_page_ranges": parse_page_ranges(exclude_pages)},
    )


class CreateAudiobookProject(BaseModel):
    title: str
    author: str = ""
    language: str = "en"


class UpdateAudiobookProject(BaseModel):
    title: str
    author: str = ""


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


class ReviseSpanAnnotation(ResolveReviewIssue):
    pass


class StartRender(BaseModel):
    provider_id: str = "faster-qwen3-tts"
    model_id: str = "Qwen3-TTS"
    model_revision: str
    generation_parameters: dict[str, object] = Field(default_factory=dict)
    seed: int | None = None


class StartPreview(StartRender):
    chapter_id: str
    span_id: str


class StartExport(BaseModel):
    format: str = "m4b"


class SetPronunciation(BaseModel):
    source_term: str
    spoken_term: str


class SetAudiobookMode(BaseModel):
    mode: str = Field(pattern="^(standard|story_only|verbatim)$")


class SetDocumentOverride(BaseModel):
    scope: str = Field(pattern="^(BLOCK|REGION|RECURRENCE_GROUP|DOCUMENT_ROLE)$")
    scope_key: str = Field(min_length=1, max_length=512)
    action: str = Field(
        default="DEFAULT", pattern="^(DEFAULT|READ|SKIP|READ_ONCE)$"
    )
    role_override: str | None = None


def _service_and_context() -> tuple["AudiobookService", Any]:
    global _SERVICE_CONTEXT
    if _SERVICE_CONTEXT is None:
        with _SERVICE_CONTEXT_LOCK:
            if _SERVICE_CONTEXT is None:
                from .service import AudiobookService

                database = default_database()
                ensure_postgresql_runtime_ready(database)
                context = bootstrap_local_tenant(database)
                _SERVICE_CONTEXT = (AudiobookService(database, LocalBlobStore()), context)
    assert _SERVICE_CONTEXT is not None
    return _SERVICE_CONTEXT


def register_audiobook_routes(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get("/api/audiobook/projects", tags=["audiobook"])
    def list_projects(offset: int = Query(default=0, ge=0)) -> dict[str, object]:
        service, context = _service_and_context()
        return {"projects": service.list_projects(context, offset=offset)}

    @gateway.get("/api/audiobook/voices", tags=["audiobook"])
    def list_voices() -> dict[str, object]:
        from .service import AudiobookService

        return {"voices": AudiobookService.list_voices()}

    @gateway.get("/api/audiobook/models/current", tags=["audiobook"])
    def audiobook_model() -> dict[str, object]:
        from .model_identity import current_model_identity

        try:
            return current_model_identity()
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @gateway.get("/api/audiobook/source-library", tags=["audiobook"])
    def source_library() -> dict[str, object]:
        return _source_library_files()

    @gateway.post("/api/audiobook/projects", tags=["audiobook"])
    def create_project(request: CreateAudiobookProject) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.create_project(context, **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.patch("/api/audiobook/projects/{project_id}", tags=["audiobook"])
    def update_project(project_id: str, request: UpdateAudiobookProject) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.update_project(context, project_id=project_id, **request.model_dump())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.delete("/api/audiobook/projects/{project_id}", tags=["audiobook"], status_code=204)
    def delete_project(project_id: str) -> Response:
        service, context = _service_and_context()
        try:
            service.delete_project(context, project_id=project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        return Response(status_code=204)

    @gateway.delete("/api/audiobook/projects/{project_id}/assets/{asset_id}", tags=["audiobook"])
    def delete_asset(project_id: str, asset_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.delete_asset(context, project_id=project_id, asset_id=asset_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @gateway.get("/api/audiobook/projects/{project_id}", tags=["audiobook"])
    def get_project(project_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.get_project(context, project_id, include_text=False)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.get("/api/audiobook/projects/{project_id}/chapters/{chapter_id}", tags=["audiobook"])
    def get_chapter(project_id: str, chapter_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.get_chapter(context, project_id=project_id,
                                       chapter_id=chapter_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook chapter not found") from exc

    @gateway.get(
        "/api/audiobook/projects/{project_id}/document-structure",
        tags=["audiobook"],
    )
    def get_document_structure(
        project_id: str, chapter_id: str | None = Query(default=None),
    ) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.get_document_structure(
                context, project_id=project_id, chapter_id=chapter_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="audiobook project not found"
            ) from exc

    @gateway.patch(
        "/api/audiobook/projects/{project_id}/reading-policy",
        tags=["audiobook"],
    )
    def set_reading_policy(
        project_id: str, request: SetAudiobookMode,
    ) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.set_audiobook_mode(
                context, project_id=project_id, mode=request.mode,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="audiobook project not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.post(
        "/api/audiobook/projects/{project_id}/document-overrides",
        tags=["audiobook"],
    )
    def set_document_override(
        project_id: str, request: SetDocumentOverride,
    ) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.set_document_override(
                context, project_id=project_id, **request.model_dump(),
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="audiobook project not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/source", tags=["audiobook"], status_code=202)
    async def upload_source(
        project_id: str, request: Request,
        source_format: str = Query(pattern=_SOURCE_FORMAT_PATTERN),
        filename: str = Query(default="book"),
        exclude_pages: str | None = Query(default=None, max_length=500),
    ) -> dict[str, str]:
        from .extraction import MAX_SOURCE_BYTES, UnsupportedSource

        if int(request.headers.get("content-length", "0") or 0) > MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="source is too large")
        content = await request.body()
        if len(content) > MAX_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="source is too large")
        service, context = await asyncio.to_thread(_service_and_context)
        try:
            extraction_settings = _page_extraction_settings(source_format, exclude_pages)
            return await asyncio.to_thread(
                service.submit_source, context, project_id=project_id,
                source_format=source_format, content=content, filename=filename,
                extraction_settings=extraction_settings,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        except UnsupportedSource as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/source/library", tags=["audiobook"], status_code=202)
    async def import_library_source(
        project_id: str, filename: str = Query(min_length=1),
        exclude_pages: str | None = Query(default=None, max_length=500),
    ) -> dict[str, str]:
        from .extraction import MAX_SOURCE_BYTES, UnsupportedSource

        try:
            path = _resolve_source_library_file(filename)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="source file not found in audiobook directory") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            if path.stat().st_size > MAX_SOURCE_BYTES:
                raise HTTPException(status_code=413, detail="source is too large")
            content = await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            raise HTTPException(status_code=409, detail="source file could not be read") from exc
        service, context = await asyncio.to_thread(_service_and_context)
        try:
            source_format = path.suffix.lower().lstrip(".")
            extraction_settings = _page_extraction_settings(source_format, exclude_pages)
            return await asyncio.to_thread(
                service.submit_source, context, project_id=project_id,
                source_format=source_format, content=content, filename=path.name,
                extraction_settings=extraction_settings,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        except UnsupportedSource as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.get("/api/audiobook/projects/{project_id}/source/download", tags=["audiobook"])
    def download_source(project_id: str) -> StreamingResponse:
        service, context = _service_and_context()
        try:
            handle, mime, filename = service.open_source(context, project_id=project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook source not found") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="audiobook source failed integrity verification") from exc

        def chunks():
            with handle:
                while chunk := handle.read(1024 * 1024):
                    yield chunk

        safe_filename = filename.replace('"', '').replace('\r', '').replace('\n', '')
        suffix = Path(safe_filename).suffix.lower().lstrip('.')
        fallback_name = f"audiobook.{suffix}" if suffix in SUPPORTED_SOURCE_FORMATS else "audiobook"
        return StreamingResponse(chunks(), media_type=mime,
                                 background=BackgroundTask(handle.close), headers={
            "Content-Length": str(os.fstat(handle.fileno()).st_size),
            "Content-Disposition": (
                f'attachment; filename="{fallback_name}"; filename*=UTF-8\'\'{quote(safe_filename, safe="")}'
            ),
        })

    @gateway.post("/api/audiobook/projects/{project_id}/cover", tags=["audiobook"])
    async def upload_cover(project_id: str, request: Request,
                           filename: str = Query(default="cover")) -> dict[str, str]:
        if int(request.headers.get("content-length", "0") or 0) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="cover is too large")
        content = await request.body()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="cover is too large")
        service, context = await asyncio.to_thread(_service_and_context)
        try:
            return await asyncio.to_thread(service.set_cover, context,
                                           project_id=project_id, content=content,
                                           filename=filename)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @gateway.get("/api/audiobook/projects/{project_id}/cover", tags=["audiobook"])
    def project_cover(project_id: str) -> Response:
        service, context = _service_and_context()
        try:
            content, mime = service.read_cover(context, project_id=project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook cover not found") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="audiobook cover failed integrity verification") from exc
        return Response(content, media_type=mime)

    @gateway.post("/api/audiobook/projects/{project_id}/speakers", tags=["audiobook"])
    def add_speaker(project_id: str, request: CreateSpeaker) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.add_speaker(context, project_id=project_id, **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

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

    @gateway.post(
        "/api/audiobook/projects/{project_id}/speakers/{speaker_id}/reject",
        tags=["audiobook"],
    )
    def reject_speaker(project_id: str, speaker_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.reject_speaker(
                context, project_id=project_id, speaker_id=speaker_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="speaker not found") from exc

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
    def confirm_alias(project_id: str, speaker_id: str, request: ConfirmSpeakerAlias) -> dict[str, object]:
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

    @gateway.post("/api/audiobook/projects/{project_id}/spans/{span_id}/annotation", tags=["audiobook"])
    def revise_span(project_id: str, span_id: str, request: ReviseSpanAnnotation) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.revise_span(context, project_id=project_id,
                                       span_id=span_id, **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="span or speaker not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/render", tags=["audiobook"], status_code=202)
    def start_render(project_id: str, request: StartRender) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.start_render(context, project_id=project_id, **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/jobs/{job_id}/cancel", tags=["audiobook"])
    def cancel_audiobook_job(project_id: str, job_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.cancel_job(context, project_id=project_id, job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook job not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/jobs/{job_id}/pause", tags=["audiobook"])
    def pause_audiobook_job(project_id: str, job_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.pause_job(context, project_id=project_id, job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/jobs/{job_id}/resume", tags=["audiobook"])
    def resume_audiobook_job(project_id: str, job_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.resume_job(context, project_id=project_id, job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/render/pause", tags=["audiobook"])
    def pause_audiobook_render_queue(project_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.pause_render_queue(context, project_id=project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/render/resume", tags=["audiobook"])
    def resume_audiobook_render_queue(project_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.pause_render_queue(context, project_id=project_id, resume=True)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/render/stop", tags=["audiobook"])
    def stop_audiobook_render_queue(project_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.stop_render_queue(context, project_id=project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.post("/api/audiobook/projects/{project_id}/jobs/{job_id}/retry", tags=["audiobook"], status_code=202)
    def retry_audiobook_job(project_id: str, job_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return service.retry_pipeline_job(context, project_id=project_id, job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/reclassify", tags=["audiobook"], status_code=202)
    def reclassify_audiobook(project_id: str) -> dict[str, str]:
        service, context = _service_and_context()
        try:
            return service.reclassify_source(context, project_id=project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @gateway.post("/api/audiobook/projects/{project_id}/preview", tags=["audiobook"], status_code=202)
    def start_preview(project_id: str, request: StartPreview) -> dict[str, str]:
        service, context = _service_and_context()
        try:
            return service.start_preview(context, project_id=project_id,
                                         **request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.get("/api/audiobook/projects/{project_id}/previews/{job_id}/audio", tags=["audiobook"])
    def preview_audio(project_id: str, job_id: str) -> Response:
        service, context = _service_and_context()
        try:
            content = service.read_preview(context, project_id=project_id,
                                           job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="preview audio not found") from exc
        return Response(content, media_type="audio/wav")

    @gateway.post("/api/audiobook/projects/{project_id}/exports", tags=["audiobook"], status_code=202)
    def start_export(project_id: str, request: StartExport) -> dict[str, str]:
        service, context = _service_and_context()
        try:
            return service.start_export(context, project_id=project_id, format=request.format)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail="audiobook asset is unavailable") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.get("/api/audiobook/projects/{project_id}/exports", tags=["audiobook"])
    def list_exports(project_id: str) -> dict[str, object]:
        service, context = _service_and_context()
        try:
            return {"exports": service.list_exports(context, project_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook project not found") from exc

    @gateway.get("/api/audiobook/projects/{project_id}/exports/{export_id}/download", tags=["audiobook"])
    def download_export(project_id: str, export_id: str) -> StreamingResponse:
        service, context = _service_and_context()
        try:
            handle, mime, format = service.open_export(
                context, project_id=project_id, export_id=export_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audiobook export not found") from exc
        def chunks():
            with handle:
                while chunk := handle.read(1024 * 1024):
                    yield chunk

        return StreamingResponse(chunks(), media_type=mime,
                                 background=BackgroundTask(handle.close), headers={
            "Content-Length": str(os.fstat(handle.fileno()).st_size),
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
    preview_thread: threading.Thread | None = None

    def worker_runtime() -> tuple[Any, Any] | None:
        while not stop.is_set():
            try:
                return _service_and_context()
            except Exception:
                _LOG.exception("Audiobook worker could not initialize its runtime")
                stop.wait(5.0)
        return None

    def worker_loop() -> None:
        from .assembly_service import run_assemble_once
        from .export_service import run_export_once
        from .worker import run_analyze_once, run_ingest_once

        runtime = worker_runtime()
        if runtime is None:
            return
        service, context = runtime
        database = service.database
        blobs = LocalBlobStore()
        worker_id = f"audiobook:ingest:{uuid4().hex}"
        while not stop.is_set():
            try:
                active = run_ingest_once(database, blobs, context, worker_id=worker_id)
                if not active:
                    active = run_analyze_once(database, context, worker_id=worker_id)
                if not active:
                    active = run_assemble_once(database, blobs, context, worker_id=worker_id)
                if not active:
                    active = run_export_once(database, blobs, context, worker_id=worker_id)
                if not active:
                    stop.wait(1.0)
            except Exception:
                _LOG.exception("Audiobook ingest worker could not poll")
                stop.wait(5.0)

    def start_worker() -> None:
        nonlocal thread, render_thread, preview_thread
        stop.clear()
        thread = threading.Thread(target=worker_loop, name="audiobook-ingest", daemon=True)
        thread.start()
        render_thread = threading.Thread(target=render_worker_loop, name="audiobook-render", daemon=True)
        render_thread.start()
        preview_thread = threading.Thread(target=preview_worker_loop, name="audiobook-preview", daemon=True)
        preview_thread.start()

    def render_worker_loop() -> None:
        from .render_service import run_render_once

        runtime = worker_runtime()
        if runtime is None:
            return
        service, context = runtime
        database = service.database
        blobs = LocalBlobStore()
        worker_id = f"audiobook:render:{uuid4().hex}"
        while not stop.is_set():
            try:
                if not run_render_once(database, blobs, context, worker_id=worker_id):
                    stop.wait(1.0)
            except Exception:
                _LOG.exception("Audiobook render worker could not poll")
                stop.wait(5.0)

    def preview_worker_loop() -> None:
        from .render_service import run_preview_once

        runtime = worker_runtime()
        if runtime is None:
            return
        service, context = runtime
        database = service.database
        blobs = LocalBlobStore()
        worker_id = f"audiobook:preview:{uuid4().hex}"
        while not stop.is_set():
            try:
                if not run_preview_once(database, blobs, context, worker_id=worker_id):
                    stop.wait(1.0)
            except Exception:
                _LOG.exception("Audiobook preview worker could not poll")
                stop.wait(5.0)

    def stop_worker() -> None:
        stop.set()
        if thread is not None:
            thread.join(timeout=2.0)
        if render_thread is not None:
            render_thread.join(timeout=2.0)
        if preview_thread is not None:
            preview_thread.join(timeout=2.0)

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
