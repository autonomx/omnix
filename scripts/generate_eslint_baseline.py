"""Add precise file-level ESLint baseline disables for current web findings."""

from __future__ import annotations

import argparse
import codecs
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "src/apps/web"
ESLINT_CLI = WEB_ROOT / "node_modules/eslint/bin/eslint.js"
BASELINE_LABEL = "baseline WP-9.x"
BASELINE_RULE = re.compile(
    r"/\*\s*eslint-disable\s+(\S+)\s+--\s*baseline WP-9\.x\s*\*/"
)


def _eslint_report(node: str) -> list[dict[str, Any]]:
    if not ESLINT_CLI.is_file():
        raise FileNotFoundError("ESLint is missing; run npm ci from the repository root")
    result = subprocess.run(
        [node, str(ESLINT_CLI), ".", "--format", "json"],
        cwd=WEB_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"ESLint did not return a JSON report (exit {result.returncode}): {result.stderr}"
        ) from exc
    if not isinstance(report, list):
        raise RuntimeError("ESLint JSON report must be an array")
    return report


def _baseline_comment(rules: set[str], newline: str) -> str:
    return "".join(
        f"/* eslint-disable {rule} -- {BASELINE_LABEL} */{newline}"
        for rule in sorted(rules)
    )


def _with_baseline(source: str, comment: str, newline: str) -> str:
    if source.startswith("#!"):
        first_line, separator, remainder = source.partition("\n")
        if not separator:
            return f"{source}{newline}{comment}"
        first_line = first_line.rstrip("\r")
        return f"{first_line}{newline}{comment}{remainder}"
    return f"{comment}{source}"


def generate_baseline(node: str, *, write: bool) -> tuple[int, int]:
    report = _eslint_report(node)
    updates = 0
    finding_files = 0
    for entry in report:
        messages = entry.get("messages", [])
        if not messages:
            continue
        path = Path(entry["filePath"]).resolve()
        try:
            path.relative_to(WEB_ROOT.resolve())
        except ValueError as exc:
            raise RuntimeError(
                f"ESLint found baseline work outside the web package: {path}"
            ) from exc

        rules: set[str] = set()
        for message in messages:
            rule = message.get("ruleId")
            if rule is None and str(message.get("message", "")).startswith(
                "Unused eslint-disable directive"
            ):
                continue
            if not isinstance(rule, str):
                raise RuntimeError(
                    f"Cannot baseline a parser/configuration error in {path}: {message.get('message')}"
                )
            rules.add(rule)
        if not rules:
            continue
        finding_files += 1
        raw = path.read_bytes()
        has_bom = raw.startswith(codecs.BOM_UTF8)
        source = raw.decode("utf-8-sig")
        existing_rules = set(BASELINE_RULE.findall(source))
        missing_rules = rules - existing_rules
        if not missing_rules:
            continue
        newline = "\r\n" if "\r\n" in source else "\n"
        rewritten = _with_baseline(
            source,
            _baseline_comment(missing_rules, newline),
            newline,
        )
        updates += 1
        if write:
            encoded = rewritten.encode("utf-8")
            path.write_bytes(codecs.BOM_UTF8 + encoded if has_bom else encoded)
        else:
            print(path.relative_to(ROOT).as_posix())
    return updates, finding_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write baseline comments into affected source files; default is a dry run",
    )
    parser.add_argument("--node", default="node", help="Node.js executable")
    args = parser.parse_args(argv)
    try:
        updates, finding_files = generate_baseline(args.node, write=args.write)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"ESLint baseline generation failed: {exc}", file=sys.stderr)
        return 2
    action = "updated" if args.write else "would update"
    print(f"{action} {updates} of {finding_files} files with findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
