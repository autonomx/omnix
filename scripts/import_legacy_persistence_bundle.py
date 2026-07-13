from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import database_settings
from app.persistence.cutover import PostgresLegacyImporter, preflight_bundle
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant


def _bundle(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("legacy bundle must contain a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import and cut over Omnix legacy persistence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("bundle", type=Path)

    import_command = subparsers.add_parser("import")
    import_command.add_argument("bundle", type=Path)
    import_command.add_argument("--dry-run", action="store_true")
    import_command.add_argument("--blob-root", type=Path)

    subparsers.add_parser("status")

    activate = subparsers.add_parser("activate")
    activate.add_argument("run_id")
    activate.add_argument("--note", default="")

    rollback = subparsers.add_parser("record-rollback")
    rollback.add_argument("run_id")
    rollback.add_argument("--reason", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "preflight":
        report = preflight_bundle(_bundle(args.bundle))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["ok"] else 1

    database = PostgresDatabase(database_settings())
    try:
        importer = PostgresLegacyImporter(
            database,
            blob_store=LocalBlobStore(getattr(args, "blob_root", None)),
        )
        if args.command == "status":
            report = importer.cutover_status()
        elif args.command == "import":
            context = bootstrap_local_tenant(database)
            report = importer.import_bundle(
                context,
                _bundle(args.bundle),
                dry_run=args.dry_run,
            )
        elif args.command == "activate":
            report = importer.activate_cutover(
                run_id=args.run_id,
                metadata={"operator_note": args.note} if args.note else {},
            )
        elif args.command == "record-rollback":
            report = importer.record_rollback(run_id=args.run_id, reason=args.reason)
        else:  # pragma: no cover
            raise RuntimeError(f"unsupported command: {args.command}")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok", True) else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": exc.__class__.__name__,
                    "message": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
