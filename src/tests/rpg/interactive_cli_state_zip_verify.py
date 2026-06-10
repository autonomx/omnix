"""Phase 13.75 — standalone verifier for stateful interactive CLI ZIP artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg.interactive_cli_campaign_state import verify_state_checkpoints_in_zip  # noqa: E402

STATE_ZIP_VERIFY_SUMMARY_VERSION = "interactive_cli_state_zip_verify_summary_v1"


def write_state_zip_verification_summary(*, result: Mapping[str, Any], summary_path: str | Path) -> Path:
    """Write the verifier result to a deterministic machine-readable JSON file."""

    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    payload["summary_format_version"] = STATE_ZIP_VERIFY_SUMMARY_VERSION
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify state checkpoint artifacts inside a stateful interactive CLI ZIP.")
    parser.add_argument("zip_path", help="Path to interactive-campaign-results.zip or an uploaded ZIP artifact.")
    parser.add_argument("--summary-path", default="", help="Optional path for writing the structured verification JSON result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = verify_state_checkpoints_in_zip(Path(args.zip_path))
    if args.summary_path:
        write_state_zip_verification_summary(result=result, summary_path=Path(args.summary_path))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
