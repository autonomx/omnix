"""Refresh the progress numbers in the TradingView parity roadmap's section 9.

Rewrites two marked blocks in ``docs/trading/TRADINGVIEW_PARITY_ROADMAP_2026-10-08.md``:

- ``parity-completion``: the completion table. Feature percentages come from
  the parity ledger (have counts 1, partial 0.5, of the features in scope);
  work packages from section 9's status table (rows whose status is exactly
  ``**Done**``) against every ``#### TVP-`` heading; the gap closed against
  the first ledger count.
- ``parity-report``: the area and tier tables of ``tradingview_parity_report.py``.

Prints ``updated`` or ``unchanged``. ``--check`` changes nothing and exits 1
when the roadmap is out of date.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.tradingview_parity_report import (  # noqa: E402
    DEFAULT_LEDGER,
    LedgerError,
    done_percent,
    load_ledger,
    render,
    summarize,
    validate,
)

DEFAULT_ROADMAP = Path("docs/trading/TRADINGVIEW_PARITY_ROADMAP_2026-10-08.md")
# Missing daily + weekly features at the first ledger count (TVP-0.1).
BASELINE_DAILY_WEEKLY_MISSING = 150

WP_HEADING = re.compile(r"^#### TVP-(\d+\.\d+[a-z]?) ", re.MULTILINE)
WP_RANGE = re.compile(r"(\d+)\.(\d+)\s*[–-]\s*(\d+)\.(\d+)")
WP_ID = re.compile(r"\d+\.\d+[a-z]?")


def expand_work_packages(cell: str) -> list[str]:
    """Work package ids in a status-table cell: ``TVP-2.1 + 2.3 + 2.4``, ``TVP-5.1–5.3``."""
    text = cell.replace("TVP-", "")
    ids: list[str] = []
    for match in WP_RANGE.finditer(text):
        phase, first, end_phase, last = (int(value) for value in match.groups())
        if phase == end_phase:
            ids += [f"{phase}.{minor}" for minor in range(first, last + 1)]
    text = WP_RANGE.sub(" ", text)
    ids += WP_ID.findall(text)
    return list(dict.fromkeys(ids))


def progress_section(roadmap: str) -> str:
    start = roadmap.index("## 9. Progress")
    end = roadmap.find("\n## ", start + 1)
    return roadmap[start:] if end < 0 else roadmap[start:end]


def done_work_packages(roadmap: str) -> list[str]:
    done: list[str] = []
    for line in progress_section(roadmap).splitlines():
        if not line.startswith("| TVP-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[1] == "**Done**":
            done += expand_work_packages(cells[0])
    return list(dict.fromkeys(done))


def _percent(part: int, whole: int) -> str:
    return "—" if whole == 0 else f"{int(100 * part / whole + 0.5)}%"


def completion_block(entries: Sequence[dict], roadmap: str) -> str:
    summary = summarize(entries)
    total: Counter[str] = Counter()
    for counts in summary.by_tier.values():
        total.update(counts)
    daily_weekly: Counter[str] = Counter()
    for tier in ("daily", "weekly"):
        daily_weekly.update(summary.by_tier[tier])
    work_packages = WP_HEADING.findall(roadmap)
    done = [wp for wp in done_work_packages(roadmap) if wp in work_packages]
    closed = max(0, BASELINE_DAILY_WEEKLY_MISSING - summary.daily_weekly_missing)
    rows = [
        ("TradingView parity, all features in scope", done_percent(total["have"], total["partial"], total["missing"])),
        (
            "TradingView parity, daily + weekly features",
            done_percent(daily_weekly["have"], daily_weekly["partial"], daily_weekly["missing"]),
        ),
        (
            "Roadmap work packages merged in full",
            f"{_percent(len(done), len(work_packages))} ({len(done)} of {len(work_packages)})",
        ),
        (
            "Daily + weekly gap closed since the first count",
            f"{_percent(closed, BASELINE_DAILY_WEEKLY_MISSING)} ({closed} of {BASELINE_DAILY_WEEKLY_MISSING})",
        ),
    ]
    lines = ["| Measure | Done |", "|---|---|"] + [f"| {name} | {value} |" for name, value in rows]
    lines += [
        "",
        "Features: have counts 1, partial 0.5, missing 0; features excluded or waiting for a decision are left out, "
        "and what Omnix had before this roadmap is included. Work packages: rows marked **Done** in the status table "
        f"below, of every TVP work package in this roadmap (including the deferred TVP-4.6). Gap: missing daily + weekly "
        f"features against {BASELINE_DAILY_WEEKLY_MISSING} at the first ledger count. Refreshed by "
        "`python scripts/tradingview_parity_progress.py`.",
    ]
    return "\n".join(lines)


def report_block(entries: Sequence[dict], ledger: str) -> str:
    text = render(summarize(entries), ledger)
    return text[text.index("| Area"):]


def replace_block(document: str, name: str, body: str) -> str:
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    first = document.index(start) + len(start)
    last = document.index(end, first)
    return document[:first] + "\n" + body.strip() + "\n" + document[last:]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="exit 1 when the roadmap is out of date; change nothing")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    roadmap_path = root / DEFAULT_ROADMAP
    try:
        entries = load_ledger(root / DEFAULT_LEDGER)
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    errors = validate(entries, root)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    roadmap = roadmap_path.read_text(encoding="utf-8")
    updated = replace_block(roadmap, "parity-completion", completion_block(entries, roadmap))
    updated = replace_block(updated, "parity-report", report_block(entries, DEFAULT_LEDGER.as_posix()))
    if updated == roadmap:
        print("unchanged")
        return 0
    if args.check:
        print("out of date: run python scripts/tradingview_parity_progress.py", file=sys.stderr)
        return 1
    roadmap_path.write_text(updated, encoding="utf-8", newline="\n")
    print("updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
