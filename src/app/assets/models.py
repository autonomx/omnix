"""Shared asset model for generated and imported Omnix artifacts."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AssetType(str, Enum):
    AUDIO = "audio"
    VOICE_SAMPLE = "voice_sample"
    VOICE_PROFILE = "voice_profile"
    IMAGE = "image"
    TRANSCRIPT = "transcript"
    STORY = "story"
    PODCAST_SCRIPT = "podcast_script"
    REPORT = "report"
    RPG_CHECKPOINT = "rpg_checkpoint"
    RUN_LOG = "run_log"
    EXPORT = "export"
    SETTINGS_ARTIFACT = "settings_artifact"


class AssetRecord(BaseModel):
    id: str
    owner_id: str | None = None
    module: str
    type: AssetType
    mime_type: str
    storage_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_job_id: str | None = None
    parent_asset_ids: list[str] = Field(default_factory=list)
    derived_asset_ids: list[str] = Field(default_factory=list)
    created_at: str
    compat: dict[str, Any] = Field(default_factory=dict)


class AssetListResponse(BaseModel):
    assets: list[AssetRecord]


class AssetMigrationPreview(BaseModel):
    source: str
    would_import: int
    missing_files: list[dict[str, Any]] = Field(default_factory=list)
    assets: list[AssetRecord] = Field(default_factory=list)
