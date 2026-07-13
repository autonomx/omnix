from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.persistence.legacy_backup import create_backup, rehearse_restore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and restore a verified backup of legacy Omnix persistence"
    )
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("sources", type=Path, nargs="+")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    create_backup(args.sources, args.backup_root)
    report = rehearse_restore(args.backup_root)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
