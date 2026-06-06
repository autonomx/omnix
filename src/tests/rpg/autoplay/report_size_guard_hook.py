"""Install a report-size guard that survives forced autoplay exits."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional

from app.rpg.autoplay_report_size_guard import cap_oversized_autoplay_reports

_INSTALLED = False
_ORIGINAL_EXIT = os._exit


def _output_dir_from_argv(argv: Iterable[str]) -> Optional[Path]:
    args: List[str] = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _latest_zip(output_dir: Path) -> Optional[Path]:
    candidates = sorted(output_dir.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def run_report_size_guard_from_argv(argv: Iterable[str]) -> dict:
    output_dir = _output_dir_from_argv(argv)
    if output_dir is None:
        return {"ok": False, "reason": "output_dir_not_found", "source": "force_exit_report_size_guard"}
    zip_path = _latest_zip(output_dir) if output_dir.exists() else None
    return cap_oversized_autoplay_reports(output_dir, zip_paths=[zip_path] if zip_path else [])


def install_force_exit_report_size_guard(argv: Iterable[str]) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    captured_argv = list(argv)

    def guarded_exit(code: int = 0) -> None:
        try:
            run_report_size_guard_from_argv(captured_argv)
        finally:
            _ORIGINAL_EXIT(code)

    os._exit = guarded_exit  # type: ignore[assignment]
    _INSTALLED = True
