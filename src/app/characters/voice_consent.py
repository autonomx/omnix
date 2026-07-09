"""Ownership, consent, provenance, and allowed-use enforcement for cloned voices."""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.assets import AssetRecord, AssetType, SharedAssetStore, default_asset_store

VoiceConsentStatus = Literal["unverified", "granted", "revoked"]
VoiceDeletionState = Literal["active", "pending_deletion", "deleted"]
VoiceAllowedUse = Literal["character", "live_call", "system_assistant", "general_tts"]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class VoiceProfileGovernance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    subject_owner: str = Field(default="", max_length=300)
    source_type: str = Field(default="unknown", max_length=120)
    source_reference: str = Field(default="", max_length=1000)
    creator_id: str = Field(default="", max_length=200)
    consent_status: VoiceConsentStatus = "unverified"
    consent_recorded_at: str | None = None
    allowed_uses: list[VoiceAllowedUse] = Field(default_factory=list)
    source_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    deletion_state: VoiceDeletionState = "active"
    deletion_requested_at: str | None = None
    deleted_at: str | None = None
    deletion_reason: str = Field(default="", max_length=1000)
    updated_at: str


class UpdateVoiceProfileGovernanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_owner: str = Field(min_length=1, max_length=300)
    source_type: str = Field(min_length=1, max_length=120)
    source_reference: str = Field(default="", max_length=1000)
    creator_id: str = Field(min_length=1, max_length=200)
    consent_status: VoiceConsentStatus
    allowed_uses: list[VoiceAllowedUse] = Field(default_factory=list)
    deletion_state: VoiceDeletionState = "active"
    deletion_reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_consent(self) -> "UpdateVoiceProfileGovernanceRequest":
        if self.consent_status == "granted" and not self.allowed_uses:
            raise ValueError("granted consent requires at least one allowed use")
        if self.deletion_state != "active" and not self.deletion_reason.strip():
            raise ValueError("voice deletion state requires a reason")
        return self


class VoiceConsentError(ValueError):
    pass


class VoiceProfileGovernanceService:
    def __init__(
        self,
        *,
        asset_store_factory: Callable[[], SharedAssetStore] = default_asset_store,
    ) -> None:
        self.asset_store_factory = asset_store_factory

    def get(self, asset_id: str) -> VoiceProfileGovernance:
        asset = self._get_asset(asset_id)
        return governance_from_asset(asset)

    def update(
        self,
        asset_id: str,
        request: UpdateVoiceProfileGovernanceRequest,
    ) -> VoiceProfileGovernance:
        store = self.asset_store_factory()
        asset = self._get_asset(asset_id, store=store)
        now = _utcnow()
        current = governance_from_asset(asset)
        consent_recorded_at = current.consent_recorded_at
        if request.consent_status == "granted" and current.consent_status != "granted":
            consent_recorded_at = now
        deletion_requested_at = current.deletion_requested_at
        deleted_at = current.deleted_at
        if request.deletion_state == "pending_deletion" and current.deletion_state != "pending_deletion":
            deletion_requested_at = now
        if request.deletion_state == "deleted" and current.deletion_state != "deleted":
            deleted_at = now
        if request.deletion_state == "active":
            deletion_requested_at = None
            deleted_at = None
        governance = VoiceProfileGovernance(
            asset_id=asset.id,
            subject_owner=request.subject_owner.strip(),
            source_type=request.source_type.strip(),
            source_reference=request.source_reference.strip(),
            creator_id=request.creator_id.strip(),
            consent_status=request.consent_status,
            consent_recorded_at=consent_recorded_at,
            allowed_uses=sorted(set(request.allowed_uses)),
            source_sha256=current.source_sha256 or _file_sha256(Path(asset.storage_path)),
            deletion_state=request.deletion_state,
            deletion_requested_at=deletion_requested_at,
            deleted_at=deleted_at,
            deletion_reason=request.deletion_reason.strip(),
            updated_at=now,
        )
        metadata = dict(asset.metadata)
        metadata["voice_governance"] = governance.model_dump(mode="json")
        store.upsert_asset(asset.model_copy(update={"metadata": metadata}))
        return governance

    def validate_use(self, asset_id: str, use: VoiceAllowedUse) -> VoiceProfileGovernance:
        governance = self.get(asset_id)
        if governance.consent_status != "granted":
            raise VoiceConsentError(
                f"voice profile consent is not granted: {asset_id} ({governance.consent_status})"
            )
        if use not in governance.allowed_uses:
            raise VoiceConsentError(f"voice profile does not allow {use}: {asset_id}")
        if governance.deletion_state != "active":
            raise VoiceConsentError(
                f"voice profile is unavailable: {asset_id} ({governance.deletion_state})"
            )
        if not governance.subject_owner or not governance.creator_id:
            raise VoiceConsentError(f"voice profile ownership provenance is incomplete: {asset_id}")
        if not governance.source_sha256:
            raise VoiceConsentError(f"voice profile source hash is unavailable: {asset_id}")
        return governance

    def _get_asset(
        self,
        asset_id: str,
        *,
        store: SharedAssetStore | None = None,
    ) -> AssetRecord:
        resolved_store = store or self.asset_store_factory()
        asset = next(
            (item for item in resolved_store.list_assets().assets if item.id == asset_id),
            None,
        )
        if asset is None:
            raise VoiceConsentError(f"voice asset not found: {asset_id}")
        if asset.type != AssetType.VOICE_PROFILE:
            raise VoiceConsentError(f"asset is not a voice profile: {asset_id}")
        return asset


def governance_from_asset(asset: AssetRecord) -> VoiceProfileGovernance:
    raw = dict(asset.metadata.get("voice_governance") or {})
    path_hash = _file_sha256(Path(asset.storage_path))
    if raw:
        raw["asset_id"] = asset.id
        raw.setdefault("source_sha256", path_hash)
        raw.setdefault("updated_at", asset.created_at)
        return VoiceProfileGovernance.model_validate(raw)
    return VoiceProfileGovernance(
        asset_id=asset.id,
        subject_owner=str(asset.owner_id or ""),
        source_type="legacy_import" if asset.compat else "unknown",
        source_reference=str(asset.compat.get("legacy_manifest") or asset.storage_path),
        creator_id="",
        consent_status="unverified",
        allowed_uses=[],
        source_sha256=path_hash,
        deletion_state="active",
        updated_at=asset.created_at,
    )


def default_voice_governance_service() -> VoiceProfileGovernanceService:
    return VoiceProfileGovernanceService()


__all__ = [
    "UpdateVoiceProfileGovernanceRequest",
    "VoiceConsentError",
    "VoiceProfileGovernance",
    "VoiceProfileGovernanceService",
    "default_voice_governance_service",
    "governance_from_asset",
]
