"""Security maintenance commands."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.security.legacy_secret_import import import_legacy_secrets


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.security")
    subcommands = parser.add_subparsers(dest="command", required=True)
    importer = subcommands.add_parser("import-legacy-secrets")
    importer.add_argument("--source", type=Path)
    args = parser.parse_args()

    count, archive = import_legacy_secrets(args.source)
    if archive is None:
        sys.stdout.write("No legacy secret file found.\n")
    else:
        sys.stdout.write(f"Imported {count} credential entries; archived source at {archive}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
