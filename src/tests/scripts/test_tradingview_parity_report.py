"""The TradingView parity ledger and its report (TVP-0.1)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.tradingview_parity_report import (
    DEFAULT_LEDGER,
    done_percent,
    load_ledger,
    main,
    render,
    summarize,
    validate,
)

ROOT = Path(__file__).resolve().parents[3]


def _entry(entry_id: str, **overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": entry_id,
        "area": "Alerts",
        "feature": entry_id,
        "tier": "daily",
        "status": "missing",
        "level": "equivalent",
        "wp": "TVP-1.1",
    }
    entry.update(overrides)
    return entry


def _write_ledger(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    (tmp_path / "evidence.ts").write_text("export const ALERT_KINDS = ['price'];\n", encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return ledger


def test_the_real_ledger_is_valid_and_the_script_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "tradingview_parity_report.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "| Area | Have | Partial |" in result.stdout
    assert "Missing daily + weekly features:" in result.stdout


def test_the_real_ledger_tracks_every_tradingview_built_in_indicator() -> None:
    entries = load_ledger(ROOT / DEFAULT_LEDGER)
    tracked = {entry["indicator_id"] for entry in entries if "indicator_id" in entry}
    goldens = json.loads((ROOT / "resources/trading/indicator_goldens/index.json").read_text(encoding="utf-8"))
    golden_ids = {indicator["id"] for indicator in goldens["indicators"]}

    assert len(tracked) == 209
    assert golden_ids <= tracked
    # An indicator with goldens is implemented; "partial" records a known gap against TradingView (Seasonality).
    assert all(
        entry["status"] in {"have", "partial"}
        for entry in entries
        if entry.get("indicator_id") in golden_ids
    )
    assert validate(entries, ROOT) == []


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (_entry("a", status="have"), "needs evidence"),
        (_entry("a", status="partial", evidence=[]), "needs evidence"),
        (_entry("a", status="have", evidence=["no/such/file.ts"]), "does not exist"),
        (_entry("a", status="have", evidence=["evidence.ts#NOT_THERE"]), "not found in evidence.ts"),
        (_entry("a", status="have", evidence=["../outside.ts"]), "inside the repository"),
        (_entry("a", status="have", evidence=["Evidence.ts"]), "does not exist: Evidence.ts"),
        (_entry("a", status="have", evidence=["docs"]), "not a directory"),
        (_entry("a", status="have", evidence=["docs#ALERT_KINDS"]), "not a directory"),
        (_entry("a", status="have", evidence="evidence.ts"), "evidence must be a list"),
        (_entry("a", status="have", evidence=[3]), "non-empty strings"),
        (_entry("a", status="done"), "unknown status"),
        (_entry("a", tier="hourly"), "unknown tier"),
        (_entry("a", level="identical"), "unknown level"),
        (_entry("a", wp=""), "missing or empty field(s): wp"),
        (_entry("a", status="excluded-pending-decision"), "needs the decision id"),
        (_entry("a", status="excluded-pending-decision", decision="vendor"), "decision must be a decision id"),
    ],
)
def test_a_bad_entry_fails_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str], entry: dict[str, object], message: str) -> None:
    ledger = _write_ledger(tmp_path, [entry])

    assert main(["--ledger", str(ledger), "--root", str(tmp_path)]) == 1
    assert message in capsys.readouterr().err


def test_duplicate_ids_fail_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = _write_ledger(tmp_path, [_entry("alerts.webhook"), _entry("alerts.webhook", tier="weekly")])

    assert main(["--ledger", str(ledger), "--root", str(tmp_path)]) == 1
    assert "duplicate id" in capsys.readouterr().err


def test_a_ledger_without_entries_fails_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]", encoding="utf-8")

    assert main(["--ledger", str(ledger), "--root", str(tmp_path)]) == 1
    assert "no 'entries' list" in capsys.readouterr().err


def test_invalid_json_fails_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text('{"entries": [', encoding="utf-8")

    assert main(["--ledger", str(ledger), "--root", str(tmp_path)]) == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_a_valid_ledger_reports_counts_per_area_and_tier(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    entries = [
        _entry("alerts.price", status="have", evidence=["evidence.ts#ALERT_KINDS"]),
        _entry("alerts.webhook"),
        _entry("alerts.channels", tier="weekly"),
        _entry("alerts.minute", tier="weekly", status="partial", evidence=["evidence.ts"]),
        _entry("research.options", area="Research data", tier="rare", status="excluded-pending-decision", decision="D-6"),
        _entry("research.seasonals", area="Research data", tier="rare"),
    ]
    ledger = _write_ledger(tmp_path, entries)

    assert main(["--ledger", str(ledger), "--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "| Alerts | 1 | 1 | 1 / 1 / 0 | 0 | 0 | 38% |" in output
    assert "| Research data | 0 | 0 | 0 / 0 / 1 | 1 | 0 | 0% |" in output
    assert "| **Total** | 1 | 1 | 1 / 1 / 1 | 1 | 0 | 30% |" in output
    assert "| Rare | 0 | 0 | 1 | 1 | 0 | 2 | 0% |" in output
    assert "Missing daily + weekly features: **2**" in output
    assert "| Daily | 1 | 0 | 1 | 0 | 0 | 2 | 50% |" in output
    assert "| Weekly | 0 | 1 | 1 | 0 | 0 | 2 | 25% |" in output
    assert "**30%** overall, **38%** of daily + weekly." in output

    summary = summarize(entries)
    assert summary.daily_weekly_missing == 2
    assert render(summary, "ledger.json").startswith("Ledger: `ledger.json`, 6 features.")


def test_done_percent_counts_partial_as_half_and_ignores_out_of_scope() -> None:
    assert done_percent(1, 1, 2) == "38%"
    assert done_percent(0, 0, 0) == "—"
    assert done_percent(3, 0, 0) == "100%"


def test_done_percent_shows_100_only_when_everything_is_have() -> None:
    assert done_percent(437, 2, 0) == "99%"
    assert done_percent(999, 0, 1) == "99%"
