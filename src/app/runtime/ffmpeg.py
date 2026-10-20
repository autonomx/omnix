"""The FFmpeg executable Omnix's media work uses (audiobook export, dubbing, transcription).

``OMNIX_FFMPEG`` wins, then ``ffmpeg`` on PATH. The repository's Windows
development environment carries a pinned imageio-ffmpeg binary that the
launcher may not put on PATH; it is used before the prerequisite is reported
missing.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config.env import environment


def ffmpeg_binary(purpose: str = "media processing") -> str:
    configured = environment().get("OMNIX_FFMPEG", "").strip()
    executable = configured or shutil.which("ffmpeg")
    if not executable:
        root = Path(__file__).resolve().parents[3]
        bundled = sorted((root / "venv" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries").glob("ffmpeg*.exe"))
        if bundled:
            executable = str(bundled[-1])
    if not executable or not Path(executable).is_file():
        raise RuntimeError(f"FFmpeg is required for {purpose}")
    return str(executable)


__all__ = ["ffmpeg_binary"]
