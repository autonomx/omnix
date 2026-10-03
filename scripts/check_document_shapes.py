"""List stored documents whose shape does not match their kind (WP-5.9).

Usage: python scripts/check_document_shapes.py [--limit N]

Reads every active row of ``omnix_module_records`` across workspaces and
checks it against the shape its feature registered. Exit status 1 when any
row does not match or a stored kind has no registered shape.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# The modules that register document shapes (kept in step by
# src/tests/persistence/test_document_schemas.py).
DOCUMENT_SCHEMA_OWNERS = (
    "app.assist_core.persistence.house_state",
    "app.assistant_tools.persistence.configuration",
    "app.assistant_tools.persistence.runtime_documents",
    "app.characters.persistence.avatar_generation_repository",
    "app.characters.persistence.avatar_store",
    "app.characters.persistence.live_profile_store",
    "app.chat.persistence.assistant_turn_store",
    "app.chat.persistence.chat_runtime",
    "app.chat.persistence.evaluation_store",
    "app.chat.persistence.legacy_sessions",
    "app.persistence.model_residency",
    "app.platform.legacy_sessions",
    "app.providers.persistence.model_refresh",
    "app.research.persistence.source_store",
    "app.rpg.persistence.rpg_feature_compat",
    "app.trading.repositories",
)


def load_document_schemas() -> None:
    for name in DOCUMENT_SCHEMA_OWNERS:
        importlib.import_module(name)


def check(database, *, limit: int | None = None) -> tuple[int, list[str]]:
    from app.persistence.document_schemas import document_matches, registered_document_kinds
    from app.persistence.tenant_scope import system_scope

    known = registered_document_kinds()
    problems: list[str] = []
    checked = 0
    with system_scope("operator.cli"), database.connection() as connection:
        rows = connection.execute(
            "SELECT workspace_id, module, record_type, record_id, payload FROM omnix_module_records"
            " WHERE status = 'active' ORDER BY module, record_type, record_id"
            + (" LIMIT %s" if limit else ""),
            (limit,) if limit else (),
        )
        for workspace_id, module, record_type, record_id, payload in rows:
            checked += 1
            if (module, record_type) not in known:
                problems.append(f"{workspace_id} {module}/{record_type}/{record_id}: no registered shape")
            elif not document_matches(module, record_type, payload, record_id=record_id):
                problems.append(f"{workspace_id} {module}/{record_type}/{record_id}: shape does not match")
    return checked, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None, help="check at most this many rows")
    args = parser.parse_args(argv)
    from app.persistence.database import default_database

    load_document_schemas()
    checked, problems = check(default_database(), limit=args.limit)
    for line in problems:
        print(line)
    print(f"checked {checked} documents; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
