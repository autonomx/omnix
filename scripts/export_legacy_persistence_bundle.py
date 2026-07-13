from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.persistence.cutover import preflight_bundle
from app.persistence.legacy_export import build_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export all supported legacy Omnix persistence into a verified bundle"
    )
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-manifest", type=Path, action="append")
    parser.add_argument("--character-db", type=Path)
    parser.add_argument("--memory-db", type=Path)
    parser.add_argument("--chat-db", type=Path)
    parser.add_argument("--jobs-db", type=Path)
    parser.add_argument("--rpg-sessions-dir", type=Path)
    parser.add_argument("--settings-json", type=Path)
    parser.add_argument("--secret-references-json", type=Path)
    parser.add_argument("--providers-json", type=Path)
    parser.add_argument("--prompts-json", type=Path)
    parser.add_argument("--research-json", type=Path)
    parser.add_argument("--reports-json", type=Path)
    parser.add_argument("--module-records-json", type=Path)
    parser.add_argument(
        "--module-document",
        nargs=3,
        action="append",
        metavar=("MODULE", "RECORD_TYPE", "PATH"),
    )
    parser.add_argument(
        "--module-jsonl",
        nargs=4,
        action="append",
        metavar=("MODULE", "RECORD_TYPE", "ID_FIELD", "PATH"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bundle = build_bundle(args)
    preflight = preflight_bundle(bundle)
    report = {
        "ok": preflight["ok"],
        "output": str(args.output),
        "source_id": preflight["source_id"],
        "source_hash": preflight["source_hash"],
        "counts": preflight["counts"],
        "source_inventory": bundle.get("source_inventory") or [],
        "errors": preflight["errors"],
    }
    if not preflight["ok"]:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
