"""Operator commands for the Memory v1 -> v2 authority switch (WP-8.5).

    python -m app.platform.assistant_memory.v2.cutover status
    python -m app.platform.assistant_memory.v2.cutover activate --by <operator> --reason "<why>"
    python -m app.platform.assistant_memory.v2.cutover rollback --by <operator> --reason "<why>"

``activate`` runs only when the shadow report is ready (every v1 owner
imported, every space ``ready``) or when v1 holds no memory at all. It passes
each space's latest ready receipt to the authority store, which re-checks
them, and that v1 has not changed, under the authority lock. From then on
curated memory is read and written in v2 and v1 is read-only.

``rollback`` returns authority to v1 only while nothing has been written,
edited or forgotten under v2; otherwise it refuses, since v1 would lose or
resurrect those memories.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from app.persistence.database import PostgresDatabase, default_database
from app.persistence.tenant_scope import system_scope

from .authority import MemoryAuthorityError, PostgresMemoryV2AuthorityStore
from .runtime import MemoryV2RuntimeError, PostgresMemoryV2Runtime
from .shadow_report import MemoryV2ShadowReport, build_shadow_report


class CutoverRefused(RuntimeError):
    pass


def _v1_record_count(database: PostgresDatabase) -> int:
    with system_scope("operator.cli"), database.transaction() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM omnix_memory_records").fetchone()[0])


def ready_receipts(report: MemoryV2ShadowReport, *, v1_records: int) -> tuple[str, ...]:
    """The receipts to activate with, or why the switch must wait."""
    if report.unimported_v1_owner_count:
        raise CutoverRefused(
            f"{report.unimported_v1_owner_count} v1 memory owners are not imported; run the shadow runner"
        )
    not_ready = [space for space in report.spaces if space.status != "ready"]
    if not_ready:
        counts: dict[str, int] = {}
        for space in not_ready:
            counts[space.status] = counts.get(space.status, 0) + 1
        raise CutoverRefused(f"memory spaces are not ready: {counts}; run the shadow runner")
    if not report.spaces and v1_records:
        raise CutoverRefused("v1 holds memory but nothing is imported; run the shadow runner")
    return tuple(space.readiness.receipt_id for space in report.spaces if space.readiness is not None)


def activate(database: PostgresDatabase, *, activated_by: str, reason: str) -> dict[str, Any]:
    authority = PostgresMemoryV2AuthorityStore(database)
    with system_scope("operator.cli"):
        if authority.current().epoch.authority == "v2":
            raise CutoverRefused("Memory v2 is already authoritative")
        report = build_shadow_report(database)
        receipts = ready_receipts(report, v1_records=_v1_record_count(database))
        state = authority.activate_v2(receipts, activated_by=activated_by, reason=reason)
    return {
        "authority": state.epoch.authority,
        "epoch": state.epoch.epoch,
        "previous_epoch": state.epoch.previous_epoch,
        "receipts": list(state.readiness_receipt_ids),
        "activated_by": state.epoch.activated_by,
    }


def rollback(database: PostgresDatabase, *, activated_by: str, reason: str) -> dict[str, Any]:
    with system_scope("operator.cli"):
        state = PostgresMemoryV2Runtime(database).rollback_to_v1(activated_by=activated_by, reason=reason)
    return {"authority": state.epoch.authority, "epoch": state.epoch.epoch}


def status(database: PostgresDatabase) -> dict[str, Any]:
    with system_scope("operator.cli"):
        runtime = PostgresMemoryV2Runtime(database)
        current = runtime.current()
        report = build_shadow_report(database)
        operational = asdict(runtime.operational_status()) if current.epoch.authority == "v2" else None
        v1_records = _v1_record_count(database)
    return {
        "authority": current.epoch.authority,
        "epoch": current.epoch.epoch,
        "activated_at": current.epoch.activated_at.isoformat(),
        "activated_by": current.epoch.activated_by,
        "v1_records": v1_records,
        "spaces": len(report.spaces),
        "space_status_counts": report.status_counts,
        "unimported_v1_owner_count": report.unimported_v1_owner_count,
        "operational": operational,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Switch curated memory between Memory v1 and v2.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="authority, readiness and v2 operation")
    for name in ("activate", "rollback"):
        command = commands.add_parser(name)
        command.add_argument("--by", required=True, help="who performs the switch")
        command.add_argument("--reason", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    database = default_database()
    try:
        if args.command == "status":
            result = status(database)
        elif args.command == "activate":
            result = activate(database, activated_by=args.by, reason=args.reason)
        else:
            result = rollback(database, activated_by=args.by, reason=args.reason)
    except (CutoverRefused, MemoryAuthorityError, MemoryV2RuntimeError) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    finally:
        database.close()
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
