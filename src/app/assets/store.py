"""Manifest-backed shared asset store with compatibility read-through."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import resources_data_root

from .models import AssetListResponse, AssetMigrationPreview, AssetRecord, AssetType


_AUDIO_MIME_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return _utcnow()


def default_asset_manifest_path() -> Path:
    override = os.environ.get("OMNIX_ASSETS_MANIFEST_PATH")
    if override:
        return Path(override)
    return resources_data_root() / "assets" / "manifest.json"


def _safe_asset_segment(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    normalized = normalized.replace(":", "-")
    pieces = [piece for part in normalized.split("/") for piece in part.split()]
    return "-".join(pieces) or "unnamed"


def _safe_voice_asset_id(voice_id: str) -> str:
    return f"voice-cloning:{_safe_asset_segment(voice_id)}"


def _safe_audio_asset_id(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    scoped_path = Path(root.name) / relative
    return f"audio:{_safe_asset_segment(str(scoped_path))}"


def _legacy_audio_roots() -> list[Path]:
    override = os.environ.get("OMNIX_LEGACY_AUDIO_DIRS")
    if override:
        return [Path(part) for part in override.split(os.pathsep) if part.strip()]

    data_root = resources_data_root()
    return [
        data_root / "generated_audio",
        data_root / "tts",
        data_root / "stt",
        data_root / "voice",
        data_root / "voice_studio",
        data_root / "podcast_audio",
    ]


def _legacy_audio_module(root: Path) -> str:
    name = root.name.lower()
    if "stt" in name:
        return "stt"
    if "podcast" in name:
        return "podcast"
    if "tts" in name or "voice" in name:
        return "voice"
    return "audio"


class SharedAssetStore:
    """Small JSON manifest store for shared asset metadata."""

    def __init__(self, manifest_path: str | Path | None = None) -> None:
        self.manifest_path = Path(manifest_path) if manifest_path else default_asset_manifest_path()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def list_assets(self) -> AssetListResponse:
        assets = self._load_manifest()
        for asset in self._legacy_voice_clone_assets():
            assets.setdefault(asset.id, asset)
        for asset in self._legacy_audio_assets():
            assets.setdefault(asset.id, asset)
        return AssetListResponse(assets=list(assets.values()))

    def get_asset(self, asset_id: str) -> AssetRecord | None:
        normalized_id = str(asset_id)
        assets = self._load_manifest()
        asset = assets.get(normalized_id)
        if asset is not None:
            return asset
        for candidate in self._legacy_voice_clone_assets():
            if candidate.id == normalized_id:
                return candidate
        for candidate in self._legacy_audio_assets():
            if candidate.id == normalized_id:
                return candidate
        return None

    def upsert_asset(self, asset: AssetRecord) -> AssetRecord:
        manifest = self._load_manifest()
        manifest[asset.id] = asset
        self._save_manifest(manifest)
        return asset

    def delete_asset(self, asset_id: str, *, delete_file: bool = True) -> dict[str, Any]:
        """Delete one manifest-backed asset and, by default, its stored file."""

        manifest = self._load_manifest()
        asset = manifest.pop(str(asset_id), None)
        if asset is None:
            return {
                "ok": False,
                "asset_id": str(asset_id),
                "deleted": False,
                "file_deleted": False,
            }

        self._save_manifest(manifest)
        file_deleted = False
        file_error = ""
        path = Path(str(asset.storage_path or ""))
        if delete_file and str(asset.storage_path or "").strip() and path.is_file():
            try:
                path.unlink()
                file_deleted = True
            except OSError as exc:
                file_error = str(exc)

        result: dict[str, Any] = {
            "ok": True,
            "asset_id": asset.id,
            "deleted": True,
            "file_deleted": file_deleted,
        }
        if file_error:
            result["file_error"] = file_error
        return result

    def preview_image_manifest_import(
        self,
        image_manifest: dict[str, Any] | None = None,
    ) -> AssetMigrationPreview:
        if image_manifest is None:
            from app.image.asset_store import get_image_asset_manifest

            image_manifest = get_image_asset_manifest()

        records: list[AssetRecord] = []
        missing: list[dict[str, Any]] = []
        for asset_id, payload in dict((image_manifest or {}).get("assets") or {}).items():
            path = str((payload or {}).get("path") or "")
            record = AssetRecord(
                id=f"image:{asset_id}",
                module="image",
                type=AssetType.IMAGE,
                mime_type=str((payload or {}).get("mime_type") or "image/png"),
                storage_path=path,
                metadata=dict((payload or {}).get("metadata") or {}),
                created_at=_utcnow(),
                compat={
                    "legacy_system": "src/app/image/asset_store.py",
                    "legacy_asset_id": asset_id,
                    "legacy_hash": (payload or {}).get("hash") or "",
                },
            )
            records.append(record)
            if path and not Path(path).is_file():
                missing.append({"asset_id": asset_id, "path": path, "reason": "file_missing"})

        return AssetMigrationPreview(
            source="src/app/image/asset_store.py",
            would_import=len(records),
            missing_files=missing,
            assets=records,
        )

    def import_image_manifest_dry_run(self, image_manifest: dict[str, Any] | None = None) -> AssetMigrationPreview:
        return self.preview_image_manifest_import(image_manifest=image_manifest)

    def import_image_manifest(self, image_manifest: dict[str, Any] | None = None) -> AssetMigrationPreview:
        preview = self.preview_image_manifest_import(image_manifest=image_manifest)
        manifest = self._load_manifest()
        for asset in preview.assets:
            manifest[asset.id] = asset
        self._save_manifest(manifest)
        return preview

    def _legacy_voice_clone_assets(self) -> list[AssetRecord]:
        """Expose voice clone profiles from metadata or recover them from audio files."""
        try:
            import app.shared as shared
        except Exception:
            return []

        manifest_path = Path(getattr(shared, "VOICE_CLONES_FILE", ""))
        clones_dir = Path(getattr(shared, "VOICE_CLONES_DIR", manifest_path.parent))
        raw: Any = {}
        if manifest_path.is_file():
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                raw = {}

        for wrapper_key in ("voices", "voice_clones", "profiles"):
            if isinstance(raw, dict) and isinstance(raw.get(wrapper_key), (dict, list)):
                raw = raw[wrapper_key]
                break

        manifest_entries: dict[str, dict[str, Any]] = {}
        if isinstance(raw, list):
            for index, payload in enumerate(raw):
                if not isinstance(payload, dict):
                    continue
                name = str(
                    payload.get("profile_name")
                    or payload.get("voice_id")
                    or payload.get("voice_clone_id")
                    or f"voice-{index + 1}"
                )
                manifest_entries[name] = dict(payload)
        elif isinstance(raw, dict):
            for voice_id, payload in raw.items():
                if isinstance(payload, dict):
                    manifest_entries[str(voice_id)] = dict(payload)

        def resolve_audio_path(clone_id: str, data: dict[str, Any]) -> Path | None:
            candidates: list[Path] = []
            for key in ("source_path", "audio_path", "storage_path"):
                value = str(data.get(key) or "").strip()
                if not value:
                    continue
                path = Path(value)
                candidates.append(path)
                if not path.is_absolute():
                    candidates.append(clones_dir / path)
            clone_name = Path(clone_id).name
            if clone_name:
                direct = clones_dir / clone_name
                candidates.append(direct)
                stem = Path(clone_name).stem
                candidates.extend(clones_dir / f"{stem}{suffix}" for suffix in _AUDIO_MIME_TYPES)
            for candidate in candidates:
                if candidate.is_file() and candidate.suffix.lower() in _AUDIO_MIME_TYPES:
                    return candidate
            return None

        records: dict[str, AssetRecord] = {}
        referenced_audio_paths: set[Path] = set()
        for legacy_name, data in sorted(manifest_entries.items()):
            profile_name = str(data.get("profile_name") or legacy_name)
            voice_id = str(data.get("voice_id") or legacy_name)
            clone_id = str(data.get("voice_clone_id") or voice_id)
            audio_path = resolve_audio_path(clone_id, data)
            if audio_path is not None:
                try:
                    referenced_audio_paths.add(audio_path.resolve())
                except OSError:
                    referenced_audio_paths.add(audio_path)
            storage_path = str(audio_path or manifest_path)
            mime_type = _AUDIO_MIME_TYPES.get(audio_path.suffix.lower(), "application/octet-stream") if audio_path else "application/json"
            asset = AssetRecord(
                id=_safe_voice_asset_id(profile_name),
                module="voice-cloning",
                type=AssetType.VOICE_PROFILE,
                mime_type=mime_type,
                storage_path=storage_path,
                metadata={
                    "profile_name": profile_name,
                    "voice_id": voice_id,
                    "voice_clone_id": clone_id,
                    "speaker": data.get("speaker") or profile_name,
                    "language": data.get("language") or "",
                    "gender": data.get("gender") or "neutral",
                    "has_audio": audio_path is not None or bool(data.get("has_audio")),
                    "is_preloaded": bool(data.get("is_preloaded")),
                    "source_path": str(data.get("source_path") or ""),
                },
                created_at=_mtime_iso(audio_path or manifest_path),
                compat={
                    "legacy_system": "app.shared.VOICE_CLONES_FILE",
                    "legacy_manifest": str(manifest_path),
                    "legacy_voice_id": legacy_name,
                },
            )
            records[asset.id] = asset

        if clones_dir.is_dir():
            audio_files = sorted(
                path
                for path in clones_dir.iterdir()
                if path.is_file() and path.suffix.lower() in _AUDIO_MIME_TYPES
            )
            for audio_path in audio_files:
                try:
                    resolved_audio_path = audio_path.resolve()
                except OSError:
                    resolved_audio_path = audio_path
                if resolved_audio_path in referenced_audio_paths:
                    continue
                sidecar_data: dict[str, Any] = {}
                sidecar_path = audio_path.with_suffix(".json")
                if sidecar_path.is_file():
                    try:
                        sidecar_raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
                        if isinstance(sidecar_raw, dict):
                            sidecar_data = sidecar_raw
                    except Exception:
                        sidecar_data = {}
                profile_name = str(sidecar_data.get("profile_name") or audio_path.stem)
                voice_id = str(sidecar_data.get("voice_id") or audio_path.stem)
                asset = AssetRecord(
                    id=_safe_voice_asset_id(profile_name),
                    module="voice-cloning",
                    type=AssetType.VOICE_PROFILE,
                    mime_type=_AUDIO_MIME_TYPES.get(audio_path.suffix.lower(), "application/octet-stream"),
                    storage_path=str(audio_path),
                    metadata={
                        "profile_name": profile_name,
                        "voice_id": voice_id,
                        "voice_clone_id": voice_id,
                        "speaker": sidecar_data.get("speaker") or profile_name,
                        "language": sidecar_data.get("language") or "",
                        "gender": sidecar_data.get("gender") or "neutral",
                        "has_audio": True,
                        "is_preloaded": bool(sidecar_data.get("is_preloaded")),
                        "recovered_from_file": True,
                    },
                    created_at=_mtime_iso(audio_path),
                    compat={
                        "legacy_system": "resources/voice_clones directory scan",
                        "legacy_voice_id": voice_id,
                        "metadata_sidecar": str(sidecar_path) if sidecar_path.is_file() else "",
                    },
                )
                records.setdefault(asset.id, asset)

        return [records[asset_id] for asset_id in sorted(records)]

    def _legacy_audio_assets(self) -> list[AssetRecord]:
        """Expose legacy generated audio files without mutating the shared manifest."""
        records: list[AssetRecord] = []
        for root in _legacy_audio_roots():
            if not root.is_dir():
                continue
            module = _legacy_audio_module(root)
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                mime_type = _AUDIO_MIME_TYPES.get(suffix)
                if not mime_type:
                    continue
                try:
                    relative = str(path.relative_to(root))
                except ValueError:
                    relative = path.name
                records.append(
                    AssetRecord(
                        id=_safe_audio_asset_id(root, path),
                        module=module,
                        type=AssetType.AUDIO,
                        mime_type=mime_type,
                        storage_path=str(path),
                        metadata={
                            "filename": path.name,
                            "extension": suffix.lstrip("."),
                            "legacy_root": root.name,
                        },
                        created_at=_mtime_iso(path),
                        compat={
                            "legacy_system": "resources/data generated audio file",
                            "legacy_root": str(root),
                            "legacy_relative_path": relative,
                        },
                    )
                )
        return records

    def _load_manifest(self) -> dict[str, AssetRecord]:
        if not self.manifest_path.is_file():
            return {}
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        raw_assets = raw.get("assets") if isinstance(raw, dict) else None
        if not isinstance(raw_assets, dict):
            return {}
        assets: dict[str, AssetRecord] = {}
        for asset_id, payload in raw_assets.items():
            if not isinstance(payload, dict):
                continue
            try:
                assets[str(asset_id)] = AssetRecord(**payload)
            except Exception:
                continue
        return assets

    def _save_manifest(self, assets: dict[str, AssetRecord]) -> None:
        payload = {
            "assets": {
                asset_id: asset.model_dump(mode="json")
                for asset_id, asset in sorted(assets.items())
            }
        }
        self.manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_asset_store() -> SharedAssetStore:
    return SharedAssetStore()
