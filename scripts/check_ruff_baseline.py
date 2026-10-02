"""Check repo-wide Ruff counts against the shrinking WP-1.3 baseline."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "resources/architecture/ruff-baseline.json"


def summarize(report: Any) -> dict[str, int]:
    """Count Ruff diagnostics by rule code from Ruff's JSON report."""

    if not isinstance(report, list):
        raise ValueError("Ruff report must be a JSON array")
    counts: Counter[str] = Counter()
    for finding in report:
        if not isinstance(finding, dict):
            raise ValueError("Ruff report entries must be JSON objects")
        code = finding.get("code")
        if not isinstance(code, str) or not code:
            raise ValueError("each Ruff report entry must include a rule code")
        counts[code] += 1
    return dict(sorted(counts.items()))


def compare(current: dict[str, int], baseline: dict[str, int]) -> list[str]:
    """Require exact counts to stay fixed until reviewed baseline reductions."""

    errors: list[str] = []
    for rule in sorted(set(current) | set(baseline)):
        observed = current.get(rule, 0)
        expected = baseline.get(rule, 0)
        if observed > expected:
            errors.append(f"{rule}: increased from {expected} to {observed}")
        elif observed < expected:
            errors.append(f"{rule}: baseline is stale ({expected} recorded, {observed} observed); shrink it")
    if current.get("F821", 0) != 0:
        errors.append(f"F821: undefined names must be zero, found {current['F821']}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="Ruff JSON report")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        baseline_document = json.loads(args.baseline.read_text(encoding="utf-8"))
        if baseline_document.get("schema_version") != 1:
            raise ValueError("unsupported Ruff baseline schema")
        baseline = baseline_document.get("rule_counts")
        if not isinstance(baseline, dict) or not all(
            isinstance(rule, str) and isinstance(count, int) and count >= 0
            for rule, count in baseline.items()
        ):
            raise ValueError("Ruff baseline rule_counts must map rule codes to non-negative integers")
        current = summarize(report)
        errors = compare(current, baseline)
        print(json.dumps({"rule_counts": current, "errors": errors}, indent=2, sort_keys=True))
        if errors:
            return 1
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Ruff baseline check: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
