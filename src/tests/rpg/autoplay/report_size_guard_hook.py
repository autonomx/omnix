"""Install a report-size guard that survives forced autoplay exits."""
from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from app.rpg.autoplay_report_size_guard import cap_oversized_autoplay_reports

_INSTALLED = False
_EXIT_ARTIFACTS_RAN = False
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


def run_forced_exit_report_artifact_hooks(argv: Iterable[str]) -> dict:
    """Materialize report artifacts before a forced ``os._exit`` skips normal hooks."""

    global _EXIT_ARTIFACTS_RAN
    if _EXIT_ARTIFACTS_RAN:
        return {"ok": True, "skipped": True, "reason": "already_ran", "source": "force_exit_report_artifact_hooks"}
    _EXIT_ARTIFACTS_RAN = True
    args = list(argv)
    output_dir = _output_dir_from_argv(args)
    if output_dir is None:
        return {"ok": False, "reason": "output_dir_not_found", "source": "force_exit_report_artifact_hooks"}

    results: dict[str, object] = {"ok": True, "results_dir": str(output_dir), "source": "force_exit_report_artifact_hooks"}
    try:
        from tests.rpg.autoplay.survival_report_writer_hook import run_autoplay_survival_report_writer_hook

        results["survival_writer"] = run_autoplay_survival_report_writer_hook(
            script_path=Path(sys.argv[0]).resolve() if sys.argv else Path("src/tests/rpg/autoplay_llm_campaign.py"),
            argv=args,
            exit_code=0,
            results_dir=output_dir,
        )
    except Exception as exc:  # pragma: no cover - defensive forced-exit path
        results["survival_writer"] = {"ok": False, "error": repr(exc), "source": "force_exit_report_artifact_hooks"}

    try:
        from app.rpg.autoplay_item_report_hook import run_autoplay_item_report_hook

        zip_path = _latest_zip(output_dir) if output_dir.exists() else None
        results["item_report_writer"] = run_autoplay_item_report_hook(
            output_dir,
            zip_paths=[zip_path] if zip_path else [],
            total_turns=100,
        )
    except Exception as exc:  # pragma: no cover - defensive forced-exit path
        results["item_report_writer"] = {"ok": False, "error": repr(exc), "source": "force_exit_report_artifact_hooks"}
    return results


def install_force_exit_report_size_guard(argv: Iterable[str]) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    captured_argv = list(argv)

    def _run_exit_hooks() -> None:
        try:
            result = run_forced_exit_report_artifact_hooks(captured_argv)
            print(f"[AUTOPLAY-FORCE-EXIT-REPORT] artifact_hooks={result}", file=sys.stderr)
        except Exception as exc:  # pragma: no cover - exit guard must be defensive
            print(f"[AUTOPLAY-FORCE-EXIT-REPORT] artifact_hooks_failed={exc!r}", file=sys.stderr)
        try:
            size_result = run_report_size_guard_from_argv(captured_argv)
            print(f"[AUTOPLAY-FORCE-EXIT-REPORT] size_guard={size_result}", file=sys.stderr)
        except Exception as exc:  # pragma: no cover - exit guard must be defensive
            print(f"[AUTOPLAY-FORCE-EXIT-REPORT] size_guard_failed={exc!r}", file=sys.stderr)

    def guarded_exit(code: int = 0) -> None:
        try:
            _run_exit_hooks()
        finally:
            _ORIGINAL_EXIT(code)

    atexit.register(_run_exit_hooks)
    os._exit = guarded_exit  # type: ignore[assignment]
    _INSTALLED = True
