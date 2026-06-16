"""Storyteller shared-asset save helpers for the browser gateway."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.assets import AssetRecord, AssetType, SharedAssetStore


class SaveStoryAssetRequest(BaseModel):
    """Request body for saving the active Storyteller manuscript."""

    title: str = "Untitled story"
    content: str
    premise: str = ""
    provider_label: str = ""
    word_count: int = Field(default=0, ge=0)
    chapter_count: int = Field(default=0, ge=0)
    source_job_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SavedStoryAssetResponse(BaseModel):
    """Saved Storyteller shared asset plus the stored text."""

    asset: AssetRecord
    content: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_story_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or "untitled-story"


def _story_asset_dir(asset_store: SharedAssetStore) -> Path:
    manifest_parent = Path(asset_store.manifest_path).parent
    path = manifest_parent / "stories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_story_asset(asset_store: SharedAssetStore, request: SaveStoryAssetRequest) -> SavedStoryAssetResponse:
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="story_content_required")

    title = request.title.strip() or "Untitled story"
    slug = _safe_story_slug(title)
    unique = uuid.uuid4().hex[:12]
    created_at = _utcnow()
    timestamp = created_at.replace(":", "-").replace("+", "-")
    path = _story_asset_dir(asset_store) / f"{slug}-{timestamp}-{unique}.md"

    try:
        path.write_text(content + "\n", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail="story_asset_write_failed") from exc

    asset = AssetRecord(
        id=f"story:{slug}:{unique}",
        module="storyteller",
        type=AssetType.STORY,
        mime_type="text/markdown",
        storage_path=str(path),
        metadata={
            "title": title,
            "premise": request.premise,
            "provider_label": request.provider_label,
            "word_count": request.word_count,
            "chapter_count": request.chapter_count,
            **request.metadata,
        },
        source_job_id=request.source_job_id,
        created_at=created_at,
        compat={"contract": "storyteller_saved_asset_v1"},
    )
    asset_store.upsert_asset(asset)
    return SavedStoryAssetResponse(asset=asset, content=content)
