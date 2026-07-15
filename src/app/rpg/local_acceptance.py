"""Combine local live, dialogue-quality, and browser timing evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from app.rpg.release_finalization import local_live_acceptance_criteria
from app.rpg.release_gates import evaluate_ui_timing_release_gates

LOCAL_ACCEPTANCE_VERSION = "rpg_local_acceptance_bundle_v1"


def evaluate_local_acceptance_bundle(
    *,
    live_smoke_report: dict[str, Any],
    dialogue_quality_report: dict[str, Any],
    browser_timing_samples: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Validate evidence produced on a machine with an active provider and browser."""

    criteria = local_live_acceptance_criteria()
    failures: list[str] = []

    if live_smoke_report.get("ok") is not True:
        failures.append("live_smoke_failed")
        failures.extend(
            f"live_smoke:{item}"
            for item in live_smoke_report.get("failures") or []
        )

    if dialogue_quality_report.get("ok") is not True:
        failures.append("live_dialogue_quality_failed")
        failures.extend(
            f"dialogue:{item}"
            for item in dialogue_quality_report.get("failures") or []
        )
        failures.extend(
            f"dialogue_case:{item}"
            for item in dialogue_quality_report.get("failed_cases") or []
        )

    samples = [sample for sample in browser_timing_samples if isinstance(sample, dict)]
    ui_reports = [evaluate_ui_timing_release_gates(sample) for sample in samples]
    minimum_samples = int(criteria.get("minimum_distinct_interactions") or 3)
    if len(ui_reports) < minimum_samples:
        failures.append("insufficient_browser_timing_samples")
    if any(report.get("ok") is not True for report in ui_reports):
        failures.append("browser_visibility_timing_failed")
        for index, report in enumerate(ui_reports):
            failures.extend(
                f"browser:{index}:{item}"
                for item in report.get("failures") or []
            )

    commit_visible_values = [
        float(report["commit_to_visible_ms"])
        for report in ui_reports
        if report.get("commit_to_visible_ms") is not None
    ]
    maximum_commit_visible = max(commit_visible_values) if commit_visible_values else None

    return {
        "format_version": LOCAL_ACCEPTANCE_VERSION,
        "ok": not failures,
        "failures": sorted(set(failures)),
        "criteria": criteria,
        "live_smoke": live_smoke_report,
        "dialogue_quality": dialogue_quality_report,
        "browser_timing": {
            "sample_count": len(ui_reports),
            "maximum_commit_to_visible_ms": maximum_commit_visible,
            "reports": ui_reports,
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate complete local-only RPG release evidence.",
    )
    parser.add_argument("--live-smoke-report", required=True)
    parser.add_argument("--dialogue-quality-report", required=True)
    parser.add_argument("--browser-timing-report", required=True)
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        live_smoke = _require_object(_read_json(Path(args.live_smoke_report)), "live smoke")
        dialogue = _require_object(
            _read_json(Path(args.dialogue_quality_report)),
            "dialogue quality",
        )
        browser_payload = _read_json(Path(args.browser_timing_report))
        browser_samples = _browser_samples(browser_payload)
        report = evaluate_local_acceptance_bundle(
            live_smoke_report=live_smoke,
            dialogue_quality_report=dialogue,
            browser_timing_samples=browser_samples,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("ok") is True else 1


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object for {label}")
    return value


def _browser_samples(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    payload = _require_object(value, "browser timing")
    for key in ("samples", "reports"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
