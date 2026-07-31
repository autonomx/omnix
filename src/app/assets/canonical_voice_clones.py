"""Unconditional read-through for the canonical resources/voice_clones folder."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.runtime_paths import resources_root

from .models import AssetRecord, AssetType

LOGGER = logging.getLogger("uvicorn.error")

_AUDIO_MIME_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}
_GENERIC_AUDIO_NAMES = {"audio", "clone", "reference", "sample", "source", "voice"}


def discover_canonical_voice_clone_assets() -> list[AssetRecord]:
    """Scan the repository's canonical clone folder regardless of env overrides.

    ``OMNIX_VOICE_CLONES_DIR`` remains useful as an additional compatibility
    source, but it must never hide files physically stored in
    ``resources/voice_clones``.
    """

    clone_root = resources_root() / "voice_clones"
    files = _audio_files(clone_root)
    records: dict[str, AssetRecord] = {}

    for audio_path in files:
        profile_name = _profile_name(clone_root, audio_path)
        voice_id = _safe_segment(profile_name)
        try:
            relative_path = str(audio_path.relative_to(clone_root))
        except ValueError:
            relative_path = audio_path.name

        asset = AssetRecord(
            id=f"voice-cloning:{voice_id}",
            module="voice-cloning",
            type=AssetType.VOICE_PROFILE,
            mime_type=_AUDIO_MIME_TYPES.get(audio_path.suffix.lower(), "application/octet-stream"),
            storage_path=str(audio_path),
            metadata={
                "profile_name": profile_name,
                "voice_id": voice_id,
                "voice_clone_id": voice_id,
                "speaker": profile_name,
                "language": "",
                "gender": "neutral",
                "has_audio": True,
                "is_preloaded": False,
                "recovered_from_canonical_file": True,
                "relative_path": relative_path,
            },
            created_at=_mtime_iso(audio_path),
            compat={
                "legacy_system": "canonical resources/voice_clones directory scan",
                "legacy_voice_id": voice_id,
                "voice_clone_root": str(clone_root),
            },
        )
        records.setdefault(asset.id, asset)

    LOGGER.info(
        "[Voice Library][canonical] scanned root=%s exists=%s audio_count=%d profiles=%s",
        clone_root,
        clone_root.is_dir(),
        len(files),
        [
            {
                "id": asset.id,
                "name": asset.metadata.get("profile_name"),
                "path": asset.storage_path,
            }
            for asset in records.values()
        ][:100],
    )
    return [records[asset_id] for asset_id in sorted(records)]


def _audio_files(clone_root: Path) -> list[Path]:
    try:
        if not clone_root.is_dir():
            return []
    except OSError:
        LOGGER.exception("[Voice Library][canonical] root could not be inspected path=%s", clone_root)
        return []

    files: list[Path] = []

    def handle_walk_error(error: OSError) -> None:
        LOGGER.warning(
            "[Voice Library][canonical] directory walk error root=%s error=%s",
            clone_root,
            error,
        )

    try:
        for root, _directories, names in os.walk(clone_root, onerror=handle_walk_error):
            for name in names:
                path = Path(root) / name
                if path.suffix.lower() in _AUDIO_MIME_TYPES:
                    files.append(path)
    except OSError:
        LOGGER.exception("[Voice Library][canonical] directory walk failed root=%s", clone_root)
    return sorted(files, key=lambda path: os.path.normcase(str(path)))


def _profile_name(clone_root: Path, audio_path: Path) -> str:
    stem = audio_path.stem.strip()
    if stem.casefold() in _GENERIC_AUDIO_NAMES and audio_path.parent != clone_root:
        return audio_path.parent.name.strip() or stem or "voice"
    return stem or audio_path.parent.name.strip() or "voice"


def _safe_segment(value: str) -> str:
    normalized = value.strip().replace("\\", "/").replace(":", "-")
    pieces = [piece for part in normalized.split("/") for piece in part.split()]
    return "-".join(pieces) or "unnamed"


def _mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return datetime.now(timezone.utc).isoformat()
