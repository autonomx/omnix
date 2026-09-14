from __future__ import annotations

"""Validate historical strategy replay artifacts before interpreting P/L.

Example:

    python scripts/validate_trading_replay_completeness.py \
        --observations /path/to/observations.csv \
        --expected docs/trading/HISTORICAL_TOP5_WINNERS_2026-08-13_TO_2026-09-11.csv

The command prints a JSON completeness report and exits non-zero when the
strict observation-level evidence contract is not satisfied.
"""

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from app.trading.strategy_replay_reliability import (
    ReplayExpectedObservation,
    assess_replay_completeness,
    replay_observation_from_result,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail closed when a trading replay is incomplete at symbol/session granularity."
    )
    parser.add_argument("--observations", required=True, help="Replay observations CSV")
    parser.add_argument(
        "--expected",
        required=True,
        help="Expected benchmark CSV containing session_date and symbol/instrument_id",
    )
    parser.add_argument(
        "--arm",
        action="append",
        dest="arms",
        default=None,
        help="Arm to validate; repeat for multiple arms. Defaults to all arms in observations.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON report path. The report is always printed to stdout.",
    )
    return parser.parse_args()


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value).strip())


def _instrument_id(row: dict[str, str]) -> str:
    value = str(row.get("instrument_id") or row.get("symbol") or "").strip()
    if not value:
        raise ValueError("replay row missing symbol/instrument_id")
    return value


def _read_expected(path: Path) -> tuple[ReplayExpectedObservation, ...]:
    rows: list[ReplayExpectedObservation] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                ReplayExpectedObservation(
                    session_date=_parse_date(row["session_date"]),
                    instrument_id=_instrument_id(row),
                )
            )
    if not rows:
        raise ValueError("expected benchmark contains no observations")
    return tuple(rows)


def _read_observations(path: Path):
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            arm = str(row.get("arm") or "").strip()
            if not arm:
                raise ValueError("replay observation missing arm")
            rows.append(
                replay_observation_from_result(
                    arm=arm,
                    session_date=_parse_date(row["session_date"]),
                    instrument_id=_instrument_id(row),
                    status=str(row.get("status") or ""),
                    reason=(str(row.get("reason") or "").strip() or None),
                )
            )
    if not rows:
        raise ValueError("replay observations contain no rows")
    return tuple(rows)


def main() -> int:
    args = _parse_args()
    observations = _read_observations(Path(args.observations))
    expected = _read_expected(Path(args.expected))
    arms = tuple(args.arms or sorted({row.arm for row in observations}))
    report = assess_replay_completeness(
        observations,
        expected,
        arms=arms,
    )
    payload = report.model_dump(mode="json")
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    return 0 if report.valid_for_strategy_inference else 2


if __name__ == "__main__":
    raise SystemExit(main())
