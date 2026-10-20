"""Dubbing's HTTP API: projects (created with their video), lines to review, approvals.

Steps run as durable jobs (``dub.<step>``) submitted through the jobs API; the
project records each step's state. Translations a person edits are kept as
theirs; approving a line binds it to the words and the take a person heard.
"""
from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.persistence.database import default_database
from app.runtime.tenant_context import current_tenant

from . import service
from .contracts import DubProject
from .steps import VIDEO_SUFFIXES

router = APIRouter()
MAX_VIDEO_UPLOAD_BYTES = 2 * 1024 ** 3
_SPOOL_IN_MEMORY_BYTES = 8 * 1024 * 1024
_LANGUAGE = r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$"


class DubProjectList(BaseModel):
    projects: list[DubProject]


class DubProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    target_language: str | None = Field(default=None, pattern=_LANGUAGE)
    translator: str | None = Field(default=None, max_length=64)
    engine: str | None = Field(default=None, max_length=64)
    speakers: int | None = Field(default=None, ge=0, le=8)
    # Source speaker -> library voice id; replaces the casting.
    casting: dict[str, str] | None = None


class DubLineUpdate(BaseModel):
    translation: str | None = Field(default=None, max_length=2000)
    voice_override: str | None = Field(default=None, max_length=200)


class DubApproval(BaseModel):
    line_ids: list[str] = Field(min_length=1, max_length=2000)
    approve: bool = True


class DubDeleted(BaseModel):
    deleted: bool


def _video_body() -> dict[str, Any]:
    return {"requestBody": {"required": True, "content": {"application/octet-stream": {
        "schema": {"contentMediaType": "application/octet-stream", "title": "Video Content", "type": "string"},
    }}}}


async def _spool(request: Request) -> Any:
    """The request body in a temporary file, refused once it passes the cap (chunked bodies too)."""
    try:
        declared = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="the video is over 2 GB")
    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_IN_MEMORY_BYTES)
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_VIDEO_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="the video is over 2 GB")
            spool.write(chunk)
        if not size:
            raise HTTPException(status_code=422, detail="the video is empty")
        spool.seek(0)
        return spool
    except BaseException:
        spool.close()
        raise


def _store_video(body: Any, filename: str, title: str) -> str:
    import shutil

    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.runtime.paths import resources_data_root

    suffix = Path(filename).suffix.lower()
    asset_id = f"dubbing-source:{uuid.uuid4().hex}"
    folder = resources_data_root() / "dubbing" / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{asset_id.split(':', 1)[1]}{suffix}"
    with path.open("wb") as target:
        shutil.copyfileobj(body, target, length=1024 * 1024)
    default_asset_store().upsert_asset(AssetRecord(
        id=asset_id, module="dubbing", type=AssetType.SOURCE, mime_type=VIDEO_SUFFIXES[suffix], storage_path=str(path),
        metadata={"title": title, "file_name": Path(filename).name}, created_at=datetime.now(timezone.utc).isoformat(),
        compat={"contract": "dubbing_v1"},
    ))
    return asset_id


@router.get("/api/dubbing/projects", response_model=DubProjectList)
def list_projects() -> DubProjectList:
    return DubProjectList(projects=service.list_projects(default_database(), current_tenant()))


@router.post("/api/dubbing/projects", response_model=DubProject, status_code=201, openapi_extra=_video_body())
async def create_project(
    request: Request,
    filename: str = Query(min_length=1, max_length=200),
    title: str = Query(default="", max_length=200),
    source_language: str = Query(default="en", pattern=_LANGUAGE),
    target_language: str = Query(pattern=_LANGUAGE),
    speakers: int = Query(default=0, ge=0, le=8),
    translator: str = Query(default="", max_length=64),
    engine: str = Query(default="", max_length=64),
) -> DubProject:
    """Upload the video to dub (MP4, MOV, MKV or WebM, up to 2 GB) and create its project."""
    if Path(filename).suffix.lower() not in VIDEO_SUFFIXES:
        raise HTTPException(status_code=422, detail="the video must be MP4, MOV, MKV or WebM")
    body = await _spool(request)
    name = title.strip() or Path(filename).stem
    try:
        asset_id = await asyncio.to_thread(_store_video, body, filename, name)
    finally:
        body.close()
    return await asyncio.to_thread(
        service.create_project, default_database(), current_tenant(), title=name, source_asset_id=asset_id,
        source_language=source_language, target_language=target_language, translator=translator, engine=engine,
        speakers=speakers,
    )


@router.get("/api/dubbing/projects/{project_id}", response_model=DubProject)
def get_project(project_id: str) -> DubProject:
    try:
        return service.get_project(default_database(), current_tenant(), project_id)
    except service.DubbingNotFound as exc:
        raise HTTPException(status_code=404, detail="dubbing_project_not_found") from exc


@router.patch("/api/dubbing/projects/{project_id}", response_model=DubProject)
def update_project(project_id: str, update: DubProjectUpdate) -> DubProject:
    values = update.model_dump(exclude_none=True)
    if not values:
        return get_project(project_id)
    try:
        return service.update_project(default_database(), current_tenant(), project_id, **values)
    except service.DubbingNotFound as exc:
        raise HTTPException(status_code=404, detail="dubbing_project_not_found") from exc


@router.delete("/api/dubbing/projects/{project_id}", response_model=DubDeleted)
def delete_project(project_id: str) -> DubDeleted:
    """Delete the project and its lines; the assets it made stay in the library."""
    try:
        service.delete_project(default_database(), current_tenant(), project_id)
    except service.DubbingNotFound as exc:
        raise HTTPException(status_code=404, detail="dubbing_project_not_found") from exc
    return DubDeleted(deleted=True)


@router.put("/api/dubbing/projects/{project_id}/lines/{line_id}", response_model=DubProject)
def update_line(project_id: str, line_id: str, update: DubLineUpdate) -> DubProject:
    """Edit a line's translation (it becomes the person's, and needs a new take) or its voice."""
    try:
        return service.edit_line(default_database(), current_tenant(), project_id, line_id,
                                 translation=update.translation, voice_override=update.voice_override)
    except service.DubbingNotFound as exc:
        raise HTTPException(status_code=404, detail="dubbing_line_not_found") from exc


@router.post("/api/dubbing/projects/{project_id}/approval", response_model=DubProject)
def approve_lines(project_id: str, approval: DubApproval) -> DubProject:
    try:
        return service.set_approval(default_database(), current_tenant(), project_id, approval.line_ids,
                                    approval.approve)
    except service.DubbingNotFound as exc:
        raise HTTPException(status_code=404, detail="dubbing_project_not_found") from exc
    except service.DubbingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
