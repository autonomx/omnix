"""Table ownership for ADR-0016 (PA-2.2).

Every table has one owner: a feature id, ``kernel`` or ``shared``. Tables
created by the migrations in the kernel folder are listed in the frozen
historical map (``resources/architecture/historical-table-owners.json``),
reviewed once by hand; a table created by a migration inside a module's own
``migrations/`` folder is owned by that module. The combined view is
generated, never edited:

    python scripts/table_ownership.py --write-historical   # once, then reviewed
    python scripts/table_ownership.py --check              # the lint and tests run this
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
KERNEL_MIGRATIONS = "src/app/persistence/migrations/"
HISTORICAL = "resources/architecture/historical-table-owners.json"
# Kernel tables modules may register their own rows in, with INSERT ... ON CONFLICT DO NOTHING only.
REGISTRATION_TABLES = frozenset({"omnix_retention_policies"})

# Owner by table-name prefix (after "omnix_"), reviewed in PA-2.2.
PREFIX_OWNERS = {
    "trading": "trading", "rpg": "rpg", "memory": "assistant-memory", "agent": "agent-runtime",
    "audiobook": "audiobook", "workflow": "agent-runtime", "task": "agent-runtime", "chat": "chat",
    "conversation": "chat", "companion": "companion-activity", "characters": "characters",
    "character": "characters", "research": "research",
}
# Tables whose prefix does not name their owner.
TABLE_OWNERS = {
    "omnix_prompt_templates": "shared", "omnix_provider_configs": "shared",
    "omnix_provider_status_projections": "shared", "omnix_reports": "shared",
}
_CREATE = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([a-z_][a-z0-9_]*)", re.I)
_DROP = re.compile(r"drop\s+table\s+(?:if\s+exists\s+)?([a-z_][a-z0-9_]*)", re.I)


def migration_sources(sources: dict[str, str]) -> dict[str, str]:
    return {path: text for path, text in sources.items() if path.endswith(".sql") and "/migrations/" in path}


def created_tables(sources: dict[str, str]) -> dict[str, str]:
    """Live tables and the migration path that created each."""
    created: dict[str, str] = {}
    dropped: set[str] = set()
    for path, text in sorted(migration_sources(sources).items(), key=lambda item: PurePosixPath(item[0]).name):
        for match in _CREATE.finditer(text):
            created.setdefault(match.group(1).lower(), path)
        dropped.update(match.group(1).lower() for match in _DROP.finditer(text))
    return {table: path for table, path in created.items() if table not in dropped}


def historical_owner(table: str) -> str:
    if table in TABLE_OWNERS:
        return TABLE_OWNERS[table]
    return PREFIX_OWNERS.get(table.removeprefix("omnix_").split("_", 1)[0], "kernel")


def module_owner(path: str, feature_packages: dict[str, str]) -> str | None:
    """The feature that owns a migration in its own migrations/ folder, if any."""
    folder = str(PurePosixPath(path).parent.parent)
    return feature_packages.get(folder)


def table_owners(sources: dict[str, str], historical: dict[str, dict], feature_packages: dict[str, str]) -> dict[str, str]:
    owners = {}
    for table, path in created_tables(sources).items():
        if path.startswith(KERNEL_MIGRATIONS):
            entry = historical.get(table)
            if entry is not None:
                owners[table] = entry["owner"]
        else:
            owner = module_owner(path, feature_packages)
            if owner is not None:
                owners[table] = owner
    return owners


def unowned_tables(sources: dict[str, str], historical: dict[str, dict], feature_packages: dict[str, str]) -> list[str]:
    owned = table_owners(sources, historical, feature_packages)
    return sorted(set(created_tables(sources)) - set(owned))


def load_historical(sources: dict[str, str]) -> dict[str, dict]:
    text = sources.get(HISTORICAL)
    return json.loads(text)["tables"] if text else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-historical", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "scripts"))
    from architecture_analysis import tracked_sources

    sources = tracked_sources(ROOT)
    if args.write_historical:
        tables = {
            table: {"owner": historical_owner(table), "created_by": PurePosixPath(path).stem}
            for table, path in sorted(created_tables(sources).items()) if path.startswith(KERNEL_MIGRATIONS)
        }
        (ROOT / HISTORICAL).write_text(json.dumps({
            "schema_version": 1,
            "frozen": True,
            "note": "Owners of tables created by the kernel-folder migrations (PA-2.2). Frozen: a new table "
                    "is created by its module's own migrations/ folder and owned by that module.",
            "tables": tables,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {len(tables)} historical owners")
        return 0
    if args.check:
        missing = sorted(set(created_tables(sources)) - set(load_historical(sources)))
        kernel_missing = [table for table in missing if created_tables(sources)[table].startswith(KERNEL_MIGRATIONS)]
        if kernel_missing:
            print("tables created by kernel-folder migrations without a historical owner: " + ", ".join(kernel_missing))
            return 1
        print("table ownership is complete")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
