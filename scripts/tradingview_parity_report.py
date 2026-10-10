"""Report on the TradingView parity ledger (TVP-0.1).

Reads ``docs/trading/tradingview-parity.json`` and prints, as Markdown tables,
the number of features per area and per usage tier in each status, plus the
count of missing daily and weekly features (the number roadmap rule 6 says may
never go up).

The script exits with status 1 when the ledger is invalid:
  - an entry lacks a required field, or has an unknown tier, status or level;
  - two entries share an id;
  - a ``have`` or ``partial`` entry has no evidence;
  - an evidence path does not exist with exactly that spelling (case
    included), is a directory, or the text it names is not in the file;
  - an ``excluded-pending-decision`` entry does not name its decision (``D-<n>``).

Evidence is a list of strings, each a repository-relative file path, optionally
followed by ``#`` and a piece of text that must appear in that file (a symbol,
a label or a test name).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = Path("docs/trading/tradingview-parity.json")

TIERS = ("daily", "weekly", "rare")
STATUSES = ("have", "partial", "missing", "excluded-pending-decision", "excluded")
LEVELS = ("equivalent", "functional")
NEEDS_EVIDENCE = frozenset({"have", "partial"})
REQUIRED_FIELDS = ("id", "area", "feature", "tier", "status", "level", "wp")
DECISION_ID = re.compile(r"D-\d+")


class LedgerError(Exception):
    """The ledger file cannot be read at all."""


@dataclass
class Summary:
    areas: list[str] = field(default_factory=list)
    by_area: dict[str, Counter[tuple[str, str]]] = field(default_factory=dict)
    by_tier: dict[str, Counter[str]] = field(default_factory=dict)
    total: int = 0

    @property
    def daily_weekly_missing(self) -> int:
        return self.by_tier["daily"]["missing"] + self.by_tier["weekly"]["missing"]


def load_ledger(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LedgerError(f"ledger not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"ledger is not valid JSON: {path}: {exc}") from exc
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise LedgerError(f"ledger has no 'entries' list: {path}")
    return entries


def _exists_with_exact_case(root: Path, relative: str) -> bool:
    """True when every part of the path exists with exactly this spelling.

    Windows and macOS file systems ignore case, so ``Path.exists`` alone would
    accept evidence that breaks on a case-sensitive checkout.
    """
    current = root
    for part in Path(relative).parts:
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        try:
            names = os.listdir(current)
        except (FileNotFoundError, NotADirectoryError):
            return False
        if part not in names:
            return False
        current = current / part
    return True


def _evidence_error(item: object, root: Path) -> str | None:
    if not isinstance(item, str) or not item.strip():
        return "evidence items must be non-empty strings"
    relative, _, symbol = item.partition("#")
    target = (root / relative).resolve()
    if Path(relative).is_absolute() or not target.is_relative_to(root.resolve()):
        return f"evidence path must be inside the repository: {relative}"
    if not _exists_with_exact_case(root, relative):
        return f"evidence path does not exist: {relative}"
    if not target.is_file():
        return f"evidence must be a file, not a directory: {relative}"
    if symbol:
        if symbol not in target.read_text(encoding="utf-8", errors="replace"):
            return f"evidence symbol {symbol!r} not found in {relative}"
    return None


def validate(entries: Sequence[object], root: Path = ROOT) -> list[str]:
    """Every problem in the ledger, one message per problem."""
    errors: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index}: not an object")
            continue
        label = f"entry {index} ({entry.get('id', '?')})"
        missing = [name for name in REQUIRED_FIELDS if not isinstance(entry.get(name), str) or not entry[name].strip()]
        if missing:
            errors.append(f"{label}: missing or empty field(s): {', '.join(missing)}")
        entry_id = entry.get("id")
        if isinstance(entry_id, str):
            if entry_id in seen:
                errors.append(f"{label}: duplicate id")
            seen.add(entry_id)
        if "tier" not in missing and entry["tier"] not in TIERS:
            errors.append(f"{label}: unknown tier {entry['tier']!r}")
        if "status" not in missing and entry["status"] not in STATUSES:
            errors.append(f"{label}: unknown status {entry['status']!r}")
        if "level" not in missing and entry["level"] not in LEVELS:
            errors.append(f"{label}: unknown level {entry['level']!r}")
        evidence = entry.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append(f"{label}: evidence must be a list")
            evidence = []
        if entry.get("status") in NEEDS_EVIDENCE and not evidence:
            errors.append(f"{label}: status {entry['status']!r} needs evidence")
        for item in evidence:
            problem = _evidence_error(item, root)
            if problem:
                errors.append(f"{label}: {problem}")
        decision = entry.get("decision")
        if entry.get("status") == "excluded-pending-decision" and decision is None:
            errors.append(f"{label}: excluded-pending-decision needs the decision id (e.g. D-4)")
        elif decision is not None and (not isinstance(decision, str) or not DECISION_ID.fullmatch(decision)):
            errors.append(f"{label}: decision must be a decision id like D-4, not {decision!r}")
    return errors


def summarize(entries: Sequence[dict[str, Any]]) -> Summary:
    summary = Summary(by_tier={tier: Counter() for tier in TIERS})
    for entry in entries:
        area, tier, status = entry["area"], entry["tier"], entry["status"]
        if area not in summary.by_area:
            summary.areas.append(area)
            summary.by_area[area] = Counter()
        summary.by_area[area][(status, tier)] += 1
        summary.by_area[area][(status, "*")] += 1
        summary.by_tier[tier][status] += 1
        summary.total += 1
    return summary


def done_percent(have: int, partial: int, missing: int) -> str:
    """Completion of the features in scope: have counts fully, partial half, missing not at all.

    Features excluded or waiting for a decision are not in scope. Rounds half up, but shows 100% only when every
    feature in scope is have; "—" with nothing in scope.
    """
    in_scope = have + partial + missing
    if in_scope == 0:
        return "—"
    percent = int(100 * (have + partial / 2) / in_scope + 0.5)
    return f"{min(percent, 99) if have < in_scope else percent}%"


def _area_row(name: str, counts: Counter[tuple[str, str]]) -> str:
    missing = " / ".join(str(counts[("missing", tier)]) for tier in TIERS)
    done = done_percent(counts[("have", "*")], counts[("partial", "*")], counts[("missing", "*")])
    return (
        f"| {name} | {counts[('have', '*')]} | {counts[('partial', '*')]} | {missing} "
        f"| {counts[('excluded-pending-decision', '*')]} | {counts[('excluded', '*')]} | {done} |"
    )


def render(summary: Summary, ledger: str) -> str:
    lines = [
        f"Ledger: `{ledger}`, {summary.total} features.",
        "",
        "| Area | Have | Partial | Missing (daily / weekly / rare) | Pending decision | Excluded | Done |",
        "|---|---|---|---|---|---|---|",
    ]
    total: Counter[tuple[str, str]] = Counter()
    for area in summary.areas:
        lines.append(_area_row(area, summary.by_area[area]))
        total.update(summary.by_area[area])
    lines.append(_area_row("**Total**", total))
    lines += [
        "",
        "| Tier | Have | Partial | Missing | Pending decision | Excluded | Total | Done |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for tier in TIERS:
        counts = summary.by_tier[tier]
        lines.append(
            f"| {tier.capitalize()} | {counts['have']} | {counts['partial']} | {counts['missing']} "
            f"| {counts['excluded-pending-decision']} | {counts['excluded']} | {sum(counts.values())} "
            f"| {done_percent(counts['have'], counts['partial'], counts['missing'])} |"
        )
    daily_weekly = [summary.by_tier[tier] for tier in ("daily", "weekly")]
    daily_weekly_done = done_percent(*(sum(counts[status] for counts in daily_weekly) for status in ("have", "partial", "missing")))
    overall = done_percent(total[("have", "*")], total[("partial", "*")], total[("missing", "*")])
    lines += [
        "",
        f"Missing daily + weekly features: **{summary.daily_weekly_missing}**",
        "",
        f"Done (have counts 1, partial 0.5, of the features in scope): **{overall}** overall, **{daily_weekly_done}** of daily + weekly.",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=None, help=f"ledger file (default: {DEFAULT_LEDGER.as_posix()} under --root)")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root that evidence paths are relative to")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    ledger_path = args.ledger if args.ledger is not None else root / DEFAULT_LEDGER
    try:
        entries = load_ledger(ledger_path)
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    errors = validate(entries, root)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"{len(errors)} ledger error(s)", file=sys.stderr)
        return 1
    try:
        shown = ledger_path.resolve().relative_to(root).as_posix()
    except ValueError:
        shown = str(ledger_path)
    print(render(summarize(entries), shown))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
