from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"summary_not_mapping:{path}")
    return payload


def validate(summary: Mapping[str, Any], *, expected_turns: int) -> tuple[str, ...]:
    issues: list[str] = []
    turns = int(summary.get("turns_executed") or 0)
    if turns != expected_turns:
        issues.append(f"turn_count_mismatch:{turns}!={expected_turns}")

    health = _mapping(summary.get("health"))
    metrics = _mapping(health.get("metrics"))
    real_turns = int(metrics.get("real_turn_runtime_count") or 0)
    compatibility_turns = int(metrics.get("compatibility_turn_runtime_count") or 0)
    if real_turns != expected_turns:
        issues.append(f"real_runtime_turn_count_mismatch:{real_turns}!={expected_turns}")
    if compatibility_turns != 0:
        issues.append(f"compatibility_runtime_turns:{compatibility_turns}")

    runtime_errors = summary.get("runtime_errors") or ()
    if runtime_errors:
        issues.append(f"runtime_errors:{len(runtime_errors)}")
    if summary.get("ok") is not True:
        issues.append("summary_not_ok")

    artifact_paths = _mapping(summary.get("artifact_paths"))
    transcript = str(artifact_paths.get("transcript") or "").strip()
    if not transcript:
        issues.append("missing_transcript_artifact")
    zip_path = str(artifact_paths.get("zip") or "").strip()
    if not zip_path:
        issues.append("missing_zip_artifact")

    quality = _mapping(summary.get("quality_gates"))
    if quality and quality.get("ok") is False:
        issues.append("quality_gates_failed")

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an actual RPG autoplay summary as release evidence."
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--expected-turns", type=int, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    summary = _load(args.summary)
    issues = validate(summary, expected_turns=max(1, args.expected_turns))
    report = {
        "format_version": "rpg_response_autoplay_gate_v1",
        "summary": str(args.summary),
        "expected_turns": args.expected_turns,
        "turns_executed": int(summary.get("turns_executed") or 0),
        "health_metrics": _mapping(_mapping(summary.get("health")).get("metrics")),
        "issues": list(issues),
        "passed": not issues,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
