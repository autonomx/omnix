"""Phase 13.84 — guarded reader for state ZIP aggregate verifier artifacts."""

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

from tests.rpg import interactive_cli_state_zip_verify as verify_cli

STATE_ZIP_VERIFY_AGGREGATE_REQUIRED_KEYS = frozenset({"aggregate_format_version", "ok"})


def validate_state_zip_verification_aggregate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the persisted state ZIP aggregate summary schema."""

    missing = sorted(key for key in STATE_ZIP_VERIFY_AGGREGATE_REQUIRED_KEYS if key not in payload)
    if missing:
        return {
            "ok": False,
            "error": "aggregate_required_keys_missing",
            "missing_keys": missing,
        }
    version = payload.get("aggregate_format_version")
    if version != verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION:
        return {
            "ok": False,
            "error": "aggregate_format_version_mismatch",
            "expected": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION,
            "actual": version,
        }
    if not isinstance(payload.get("ok"), bool):
        return {
            "ok": False,
            "error": "aggregate_ok_not_bool",
            "actual_type": type(payload.get("ok")).__name__,
        }
    return {
        "ok": True,
        "aggregate_format_version": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION,
    }


def read_state_zip_verification_aggregate(path: str | Path) -> dict[str, Any]:
    """Read and validate a persisted aggregate verifier artifact without raising for expected bad inputs."""

    aggregate_path = Path(path)
    if not aggregate_path.exists():
        return {
            "ok": False,
            "error": "aggregate_file_missing",
            "path": str(aggregate_path),
        }
    try:
        payload = json.loads(aggregate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error": "aggregate_json_invalid",
            "path": str(aggregate_path),
            "message": str(exc),
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "aggregate_payload_not_object",
            "path": str(aggregate_path),
            "actual_type": type(payload).__name__,
        }
    validation = validate_state_zip_verification_aggregate_payload(payload)
    if not validation.get("ok"):
        return {
            "ok": False,
            "error": validation.get("error") or "aggregate_schema_invalid",
            "path": str(aggregate_path),
            "validation": validation,
        }
    return {
        "ok": True,
        "path": str(aggregate_path),
        "aggregate": payload,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read and validate a persisted state ZIP aggregate verifier JSON artifact.")
    parser.add_argument("aggregate_path", help="Path to a persisted state ZIP aggregate JSON artifact.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = read_state_zip_verification_aggregate(Path(args.aggregate_path))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
