"""Fast ZIP member filtering for essential autoplay mirror materialization.

Large autoplay result ZIPs can contain thousands of review-artifact parts.  The
operator-facing essential unzipped mirror only needs durable top-level evidence
artifacts, so filtering review-artifact members at ZIP member enumeration time
prevents the mirror path from spending minutes skipping files it will not copy.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any, List

SOURCE = "autoplay_essential_mirror_member_filter_v1"
_REVIEW_ARTIFACT_MARKER = "/review-artifacts/"
_ZIP_NAME = "autoplay-campaign-results.zip"
_INSTALLED = False
_ORIGINAL_NAMELIST = zipfile.ZipFile.namelist
_ORIGINAL_INFOLIST = zipfile.ZipFile.infolist


def _enabled() -> bool:
    return os.environ.get("RPG_AUTOPLAY_FAST_ESSENTIAL_MIRROR", "1").strip().lower() not in {"0", "false", "no", "off"}


def _is_autoplay_results_zip(zip_file: zipfile.ZipFile) -> bool:
    filename = str(getattr(zip_file, "filename", "") or "")
    return Path(filename).name == _ZIP_NAME


def _is_review_artifact_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return normalized.startswith("review-artifacts/") or _REVIEW_ARTIFACT_MARKER in normalized


def filter_essential_mirror_member_names(names: List[str]) -> List[str]:
    return [name for name in names if not _is_review_artifact_member(str(name))]


def _guarded_namelist(self: zipfile.ZipFile) -> List[str]:
    names = list(_ORIGINAL_NAMELIST(self))
    if not _enabled() or not _is_autoplay_results_zip(self):
        return names
    return filter_essential_mirror_member_names(names)


def _guarded_infolist(self: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    infos = list(_ORIGINAL_INFOLIST(self))
    if not _enabled() or not _is_autoplay_results_zip(self):
        return infos
    return [info for info in infos if not _is_review_artifact_member(str(getattr(info, "filename", "")))]


def install_essential_mirror_member_filter() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return False
    zipfile.ZipFile.namelist = _guarded_namelist  # type: ignore[assignment]
    zipfile.ZipFile.infolist = _guarded_infolist  # type: ignore[assignment]
    _INSTALLED = True
    return True
