"""Opt-in live-worker endurance evidence collector for the web platform."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_output_dir(root: Path) -> Path:
    return root / "resources" / "data" / "test-results" / "web-platform-live-worker-endurance"


def _write_result(output_dir: Path, result: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"live-worker-endurance-{timestamp}.json"
    result["artifact_path"] = str(path)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return path


def run_live_worker_endurance(
    *,
    iterations: int,
    interval_seconds: float,
    min_reachable: int,
    allow_live: bool,
    allow_mock: bool,
    output_dir: Path,
) -> dict[str, Any]:
    if not allow_live:
        return {
            "ok": False,
            "skipped": True,
            "error": "live_worker_endurance_requires_allow_live",
            "hint": "Pass --allow-live after configuring real worker URLs.",
        }

    if not allow_mock:
        os.environ.pop("OMNIX_GATEWAY_MOCK_WORKERS", None)

    root = _repo_root()
    src_dir = root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from app.gateway.workers import get_worker_health_payload

    started_at = _utcnow()
    samples: list[dict[str, Any]] = []
    for index in range(max(1, iterations)):
        payload = get_worker_health_payload().model_dump(mode="json")
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        samples.append(
            {
                "iteration": index + 1,
                "created_at": _utcnow(),
                "ok": bool(payload.get("ok")),
                "status": payload.get("status"),
                "summary": summary,
                "diagnostics": payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else [],
                "workers": payload.get("workers") if isinstance(payload.get("workers"), list) else [],
            }
        )
        if index + 1 < max(1, iterations) and interval_seconds > 0:
            time.sleep(interval_seconds)

    failed_samples = [sample for sample in samples if not sample.get("ok")]
    reachable_counts = [int((sample.get("summary") or {}).get("reachable") or 0) for sample in samples]
    configured_counts = [int((sample.get("summary") or {}).get("configured") or 0) for sample in samples]
    minimum_reachable_seen = min(reachable_counts) if reachable_counts else 0
    minimum_configured_seen = min(configured_counts) if configured_counts else 0
    ok = (
        not failed_samples
        and minimum_configured_seen >= min_reachable
        and minimum_reachable_seen >= min_reachable
    )
    result = {
        "ok": ok,
        "skipped": False,
        "format_version": "omnix_web_live_worker_endurance_v1",
        "started_at": started_at,
        "completed_at": _utcnow(),
        "iterations": max(1, iterations),
        "interval_seconds": interval_seconds,
        "min_reachable": min_reachable,
        "allow_mock": allow_mock,
        "minimum_configured_seen": minimum_configured_seen,
        "minimum_reachable_seen": minimum_reachable_seen,
        "failed_sample_count": len(failed_samples),
        "samples": samples,
    }
    if not ok:
        result["error"] = "live_worker_endurance_failed"
    _write_result(output_dir, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true", help="Required opt-in for live worker probing.")
    parser.add_argument("--allow-mock", action="store_true", help="Allow mock workers for deterministic script tests.")
    parser.add_argument("--iterations", type=int, default=60, help="Worker health samples to collect.")
    parser.add_argument("--interval-seconds", type=float, default=10.0, help="Seconds between samples.")
    parser.add_argument("--min-reachable", type=int, default=1, help="Minimum reachable workers required in every sample.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for the JSON evidence artifact.")
    args = parser.parse_args(argv)

    root = _repo_root()
    output_dir = args.output_dir or _default_output_dir(root)
    result = run_live_worker_endurance(
        iterations=args.iterations,
        interval_seconds=args.interval_seconds,
        min_reachable=args.min_reachable,
        allow_live=args.allow_live,
        allow_mock=args.allow_mock,
        output_dir=output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("skipped"):
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
