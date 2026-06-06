"""Build an interactive intent matrix performance review from an output folder."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.rpg.interactive_matrix_performance_review import (  # noqa: E402
    write_interactive_matrix_performance_review_from_file,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an interactive matrix performance review artifact pair.")
    parser.add_argument(
        "--performance-json",
        default="",
        help="Path to interactive-intent-matrix-performance.json. Defaults to output-root/interactive-intent-matrix-performance.json.",
    )
    parser.add_argument(
        "--output-root",
        default="",
        help="Output root containing interactive-intent-matrix-performance.json.",
    )
    parser.add_argument(
        "--evidence-name",
        default="interactive-intent-matrix.zip",
        help="Evidence bundle name to record in the review.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_root = Path(args.output_root) if args.output_root else Path.cwd()
    performance_json = Path(args.performance_json) if args.performance_json else output_root / "interactive-intent-matrix-performance.json"
    if not performance_json.exists():
        print(json.dumps({"ok": False, "error": "performance_json_not_found", "path": str(performance_json)}, sort_keys=True))
        return 2
    result = write_interactive_matrix_performance_review_from_file(
        performance_json,
        output_root=output_root,
        evidence_name=args.evidence_name,
    )
    print(json.dumps({"ok": bool(result.get("ok")), "json_path": result.get("json_path"), "html_path": result.get("html_path")}, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
