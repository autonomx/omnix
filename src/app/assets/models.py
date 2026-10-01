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
    SOURCE = "source"
    COVER = "cover"
    RENDER = "render"
    CHAPTER_AUDIO = "chapter-audio"
    OTHER = "other"


class AssetRecord(BaseModel):
    id: str
    owner_id: str | None = None
    module: str
    type: AssetType
    mime_type: str
    # Local filesystem path for file-discovered or legacy assets. Blob-backed
    # assets set ``storage_key`` instead (WP-5.8); read either through
    # ``app.assets.content`` rather than opening this path directly.
    storage_path: str = ""
    storage_key: str | None = None
    checksum_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_job_id: str | None = None
    parent_asset_ids: list[str] = Field(default_factory=list)
    derived_asset_ids: list[str] = Field(default_factory=list)
    created_at: str
    compat: dict[str, Any] = Field(default_factory=dict)


class AssetContentTooLarge(ValueError):
    """Raised when a bounded asset-content read exceeds its caller's limit."""


class AssetListResponse(BaseModel):
    assets: list[AssetRecord]


class AssetMigrationPreview(BaseModel):
    source: str
    would_import: int
    missing_files: list[dict[str, Any]] = Field(default_factory=list)
    assets: list[AssetRecord] = Field(default_factory=list)


class AssetLegacyRootScan(BaseModel):
    family: str
    path: str
    exists: bool


class AssetLegacyImportDryRun(BaseModel):
    source: str
    would_import: int
    category_counts: dict[str, int] = Field(default_factory=dict)
    roots_scanned: list[AssetLegacyRootScan] = Field(default_factory=list)
    collision_asset_ids: list[str] = Field(default_factory=list)
    skipped_files: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assets: list[AssetRecord] = Field(default_factory=list)
