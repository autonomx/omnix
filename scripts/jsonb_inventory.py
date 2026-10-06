"""Generate docs/architecture/JSONB_INVENTORY.md (WP-5.9).

Columns come from the migrations (CREATE TABLE, ADD COLUMN, DROP COLUMN,
DROP TABLE); usage comes from the SQL string literals in ``src/app``:

- queried: a JSON operator (``->>``, ``->``, ``#>>``, ``@>``, ``?``) applies to
  the column in a statement that names its table;
- partially updated: ``jsonb_set(column``, ``column ||`` or ``column -`` in an
  UPDATE of its table;
- opaque: read and written whole.

Decisions for queried columns live in ``resources/architecture/jsonb-decisions.json``;
``--check`` fails when a queried column has no decision or the document is stale.

    python scripts/jsonb_inventory.py --write
    python scripts/jsonb_inventory.py --check
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/app"
DOCUMENT = ROOT / "docs/architecture/JSONB_INVENTORY.md"
DECISIONS = ROOT / "resources/architecture/jsonb-decisions.json"

_CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(", re.I)
_ALTER = re.compile(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(\w+)\s+([^;]*);", re.I)
_ADD = re.compile(r"\bADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+JSONB\b", re.I)
_RETYPE = re.compile(r"\bALTER\s+(?:COLUMN\s+)?(\w+)\s+(?:SET\s+DATA\s+)?TYPE\s+JSONB\b", re.I)
_DROP_COLUMN = re.compile(r"\bDROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?(\w+)", re.I)
_DROP_TABLE = re.compile(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w\s,]+?)(?:\s+CASCADE)?\s*;", re.I)
_COLUMN = re.compile(r"^\s*(\w+)\s+JSONB\b", re.I | re.M)
_TABLE_REF = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+(\w+)", re.I)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _body(sql: str, start: int) -> str:
    depth, index = 1, start
    while index < len(sql) and depth:
        depth += {"(": 1, ")": -1}.get(sql[index], 0)
        index += 1
    return sql[start:index - 1]


def _top_level_parts(body: str) -> list[str]:
    """Column and constraint definitions: split at commas outside () and quotes."""
    parts, depth, quoted, start = [], 0, False, 0
    for index, char in enumerate(body):
        if char == "'":
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
        elif not quoted and depth == 0 and char == ",":
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    return parts


def migration_files() -> list[Path]:
    """Every schema migration in version order, from the folders the kernel reads (PA-2.3)."""
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from app.persistence.migrations import migration_roots

    return sorted((path for folder in migration_roots() for path in folder.glob("*.sql")), key=lambda path: path.stem)


def jsonb_columns() -> dict[str, set[str]]:
    columns: dict[str, set[str]] = {}
    for path in migration_files():
        sql = _strip_comments(path.read_text(encoding="utf-8"))
        events: list[tuple[int, str, tuple[str, ...]]] = []
        for match in _CREATE.finditer(sql):
            events.append((match.start(), "create", (match.group(1).lower(), _body(sql, match.end()))))
        for match in _ALTER.finditer(sql):
            table, clauses = match.group(1).lower(), match.group(2)
            for clause in clauses.split(","):
                if added := _ADD.search(clause) or _RETYPE.search(clause):
                    events.append((match.start(), "add", (table, added.group(1).lower())))
                elif (dropped := _DROP_COLUMN.search(clause)) and dropped.group(1).upper() not in {"CONSTRAINT", "DEFAULT", "NOT"}:
                    events.append((match.start(), "drop_column", (table, dropped.group(1).lower())))
        for match in _DROP_TABLE.finditer(sql):
            for name in match.group(1).split(","):
                events.append((match.start(), "drop_table", (name.strip().lower(),)))
        for _, kind, args in sorted(events):
            if kind == "create":
                table, body = args
                found = {match.group(1).lower() for part in _top_level_parts(body) if (match := _COLUMN.match(part))}
                columns.setdefault(table, set()).update(found)
            elif kind == "add":
                columns.setdefault(args[0], set()).add(args[1])
            elif kind == "drop_column":
                columns.get(args[0], set()).discard(args[1])
            elif kind == "drop_table":
                columns.pop(args[0], None)
    return {table: names for table, names in columns.items() if names}


def sql_literals() -> list[str]:
    literals: list[str] = []
    for path in SOURCE.rglob("*.py"):
        if "vendor" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"\b(SELECT|UPDATE|INSERT|DELETE)\b", node.value):
                literals.append(node.value)
            elif isinstance(node, ast.JoinedStr):
                text = "".join(part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str))
                if re.search(r"\b(SELECT|UPDATE|INSERT|DELETE)\b", text):
                    literals.append(text)
    return literals


def classify(columns: dict[str, set[str]], literals: list[str]) -> dict[tuple[str, str], str]:
    usage: dict[tuple[str, str], str] = {(table, column): "opaque" for table, names in columns.items() for column in names}
    for sql in literals:
        tables = {name.lower() for name in _TABLE_REF.findall(sql)}
        for table in tables & set(columns):
            for column in columns[table]:
                pattern = rf"(?<![\w.])(?:\w+\.)?{column}\s*(?:->>|->|#>>|#>|@>|\?\||\?&|\?)"
                if re.search(pattern, sql):
                    usage[(table, column)] = "queried"
                elif usage[(table, column)] == "opaque" and re.search(
                    rf"jsonb_set\(\s*{column}\b|\b{column}\s*=\s*{column}\s*(?:\|\||-)", sql
                ):
                    usage[(table, column)] = "partial_update"
    return usage


def render(usage: dict[tuple[str, str], str], decisions: dict[str, str]) -> str:
    counts = {kind: sum(1 for value in usage.values() if value == kind) for kind in ("queried", "partial_update", "opaque")}
    lines = [
        "# JSONB inventory",
        "",
        "Generated by `python scripts/jsonb_inventory.py --write` (WP-5.9); do not edit by hand.",
        "Decisions for queried columns are in `resources/architecture/jsonb-decisions.json`.",
        "",
        f"- Columns: {len(usage)} ({counts['queried']} queried, {counts['partial_update']} partially updated, {counts['opaque']} opaque)",
        "- Opaque columns are read and written whole and are validated by their repository's Pydantic models.",
        "",
        "| Table | Column | Use | Decision |",
        "|---|---|---|---|",
    ]
    for (table, column), use in sorted(usage.items()):
        decision = decisions.get(f"{table}.{column}", "keep opaque" if use == "opaque" else "keep; updated in SQL" if use == "partial_update" else "")
        lines.append(f"| `{table}` | `{column}` | {use.replace('_', ' ')} | {decision} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    usage = classify(jsonb_columns(), sql_literals())
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8")) if DECISIONS.exists() else {}
    document = render(usage, decisions)
    if args.write:
        DOCUMENT.write_text(document, encoding="utf-8")
        print(f"wrote {DOCUMENT.relative_to(ROOT)}: {len(usage)} columns")
        return 0
    errors = [
        f"{table}.{column} is queried but has no decision in {DECISIONS.relative_to(ROOT)}"
        for (table, column), use in sorted(usage.items())
        if use == "queried" and f"{table}.{column}" not in decisions
    ]
    if not DOCUMENT.exists() or DOCUMENT.read_text(encoding="utf-8") != document:
        errors.append(f"{DOCUMENT.relative_to(ROOT)} is stale; run python scripts/jsonb_inventory.py --write")
    for error in errors:
        print(f"jsonb inventory: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
