"""Combine local live, dialogue-quality, and browser timing evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from app.rpg.release_finalization import local_live_acceptance_criteria
from app.rpg.release_gates import (
    evaluate_dialogue_quality_release_gates,
    evaluate_ui_timing_release_gates,
)

LOCAL_ACCEPTANCE_VERSION = "rpg_local_acceptance_bundle_v1"


def evaluate_local_acceptance_bundle(
    *,
    live_smoke_report: dict[str, Any],
    dialogue_quality_report: dict[str, Any],
    browser_timing_samples: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Validate evidence produced on a machine with an active provider/browser."""

    criteria = local_live_acceptance_criteria()
    failures: list[str] = []
    if live_smoke_report.get("ok") is not True:
        failures.append("live_smoke_failed")
        failures.extend(
            f"live_smoke:{item}"
            for item in live_smoke_report.get("failures") or []
        )

    dialogue_gate = evaluate_dialogue_quality_release_gates(dialogue_quality_report)
    if dialogue_gate.get("ok") is not True:
        failures.append("live_dialogue_quality_failed")
        failures.extend(
            f"dialogue:{item}"
            for item in dialogue_gate.get("failures") or []
        )

    samples = [sample for sample in browser_timing_samples if isinstance(sample, dict)]
    ui_reports = [evaluate_ui_timing_release_gates(sample) for sample in samples]
    if len(ui_reports) < int(criteria.get("minimum_distinct_interactions") or 3):
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
        "dialogue_quality_gate": dialogue_gate,
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
        live_smoke = _read_json(Path(args.live_smoke_report))
        dialogue = _read_json(Path(args.dialogue_quality_report))
        browser_payload = _read_json(Path(args.browser_timing_report))
        browser_samples = (
            browser_payload.get("samples")
            if isinstance(browser_payload.get("samples"), list)
            else browser_payload.get("reports")
            if isinstance(browser_payload.get("reports"), list)
            else []
        )
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
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report.get("ok") is True else 1


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
