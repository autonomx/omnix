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
STATE_ZIP_VERIFY_SUMMARY_REQUIRED_KEYS = frozenset({"summary_format_version", "ok"})
STATE_ZIP_VERIFY_STATUS_MARKER = "INTERACTIVE_CLI_STATE_ZIP_VERIFY"
STATE_ZIP_VERIFY_AGGREGATE_VERSION = "interactive_cli_state_zip_verify_aggregate_v1"


def validate_state_zip_verification_summary_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the small machine-readable summary schema emitted by this CLI."""

    missing = sorted(key for key in STATE_ZIP_VERIFY_SUMMARY_REQUIRED_KEYS if key not in payload)
    if missing:
        return {
            "ok": False,
            "error": "summary_required_keys_missing",
            "missing_keys": missing,
        }
    version = payload.get("summary_format_version")
    if version != STATE_ZIP_VERIFY_SUMMARY_VERSION:
        return {
            "ok": False,
            "error": "summary_format_version_mismatch",
            "expected": STATE_ZIP_VERIFY_SUMMARY_VERSION,
            "actual": version,
        }
    if not isinstance(payload.get("ok"), bool):
        return {
            "ok": False,
            "error": "summary_ok_not_bool",
            "actual_type": type(payload.get("ok")).__name__,
        }
    return {
        "ok": True,
        "summary_format_version": STATE_ZIP_VERIFY_SUMMARY_VERSION,
    }


def aggregate_state_zip_verification_summaries(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate validated state ZIP verifier summaries into one CI-friendly result."""

    entries: list[dict[str, Any]] = []
    valid_summary_count = 0
    invalid_summary_count = 0
    passed = 0
    failed = 0
    total_checkpoint_count = 0
    total_restored_turn_count = 0

    for index, summary in enumerate(summaries):
        payload = dict(summary)
        validation = validate_state_zip_verification_summary_payload(payload)
        entry: dict[str, Any] = {
            "index": index,
            "schema_ok": bool(validation.get("ok")),
        }
        if not validation.get("ok"):
            invalid_summary_count += 1
            failed += 1
            entry.update(
                {
                    "verification_ok": False,
                    "error": validation.get("error") or "summary_schema_invalid",
                    "validation": validation,
                }
            )
            entries.append(entry)
            continue

        valid_summary_count += 1
        verification_ok = bool(payload.get("ok"))
        checkpoint_count = _safe_int(payload.get("checkpoint_count"))
        restored_turn_count = len(payload.get("restored_turns") if isinstance(payload.get("restored_turns"), list) else [])
        total_checkpoint_count += checkpoint_count
        total_restored_turn_count += restored_turn_count
        if verification_ok:
            passed += 1
        else:
            failed += 1
        entry.update(
            {
                "verification_ok": verification_ok,
                "checkpoint_count": checkpoint_count,
                "restored_turn_count": restored_turn_count,
                "error": str(payload.get("error") or "none"),
            }
        )
        entries.append(entry)

    return {
        "aggregate_format_version": STATE_ZIP_VERIFY_AGGREGATE_VERSION,
        "ok": failed == 0 and invalid_summary_count == 0,
        "summary_count": len(summaries),
        "valid_summary_count": valid_summary_count,
        "invalid_summary_count": invalid_summary_count,
        "passed": passed,
        "failed": failed,
        "total_checkpoint_count": total_checkpoint_count,
        "total_restored_turn_count": total_restored_turn_count,
        "entries": entries,
    }


def write_state_zip_verification_aggregate(*, aggregate: Mapping[str, Any], aggregate_path: str | Path) -> Path:
    """Write an aggregate verifier result as deterministic JSON for CI artifacts."""

    payload = dict(aggregate)
    if payload.get("aggregate_format_version") != STATE_ZIP_VERIFY_AGGREGATE_VERSION:
        raise ValueError("aggregate_format_version_mismatch")
    if not isinstance(payload.get("ok"), bool):
        raise ValueError("aggregate_ok_not_bool")
    path = Path(aggregate_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return path


def read_state_zip_verification_summary(path: str | Path) -> dict[str, Any]:
    """Read a single verifier summary JSON payload from disk."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def aggregate_state_zip_verification_summary_files(paths: Sequence[str | Path]) -> dict[str, Any]:
    """Read and aggregate multiple persisted verifier summary JSON files."""

    summaries = [read_state_zip_verification_summary(path) for path in paths]
    return aggregate_state_zip_verification_summaries(summaries)


def write_state_zip_verification_summary(*, result: Mapping[str, Any], summary_path: str | Path) -> Path:
    """Write the verifier result to a deterministic machine-readable JSON file."""

    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    payload["summary_format_version"] = STATE_ZIP_VERIFY_SUMMARY_VERSION
    validation = validate_state_zip_verification_summary_payload(payload)
    if not validation.get("ok"):
        raise ValueError(str(validation.get("error") or "summary_schema_invalid"))
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return path


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def render_state_zip_verification_status_marker(result: Mapping[str, Any]) -> str:
    """Render a one-line status marker for log scraping without parsing stdout JSON."""

    ok = "true" if bool(result.get("ok")) else "false"
    checkpoint_count = _safe_int(result.get("checkpoint_count"))
    restored_turn_count = len(result.get("restored_turns") if isinstance(result.get("restored_turns"), list) else [])
    error = str(result.get("error") or "none")
    return (
        f"[{STATE_ZIP_VERIFY_STATUS_MARKER}] "
        f"ok={ok} checkpoint_count={checkpoint_count} "
        f"restored_turn_count={restored_turn_count} error={error}"
    )


def parse_state_zip_verification_status_marker(line: str) -> dict[str, Any]:
    """Parse the one-line verifier status marker emitted to stderr.

    The parser is deliberately strict about marker identity and required fields so
    automation can distinguish malformed logs from valid failure statuses.
    """

    text = str(line or "").strip()
    prefix = f"[{STATE_ZIP_VERIFY_STATUS_MARKER}] "
    if not text.startswith(prefix):
        return {
            "ok": False,
            "error": "status_marker_prefix_mismatch",
        }
    fields: dict[str, str] = {}
    for token in text[len(prefix):].split():
        if "=" not in token:
            return {
                "ok": False,
                "error": "status_marker_token_malformed",
                "token": token,
            }
        key, value = token.split("=", 1)
        if not key or key in fields:
            return {
                "ok": False,
                "error": "status_marker_key_invalid",
                "key": key,
            }
        fields[key] = value
    required = {"ok", "checkpoint_count", "restored_turn_count", "error"}
    missing = sorted(required.difference(fields))
    if missing:
        return {
            "ok": False,
            "error": "status_marker_required_keys_missing",
            "missing_keys": missing,
        }
    if fields["ok"] not in {"true", "false"}:
        return {
            "ok": False,
            "error": "status_marker_ok_invalid",
            "actual": fields["ok"],
        }
    try:
        checkpoint_count = int(fields["checkpoint_count"])
        restored_turn_count = int(fields["restored_turn_count"])
    except ValueError:
        return {
            "ok": False,
            "error": "status_marker_count_invalid",
        }
    if checkpoint_count < 0 or restored_turn_count < 0:
        return {
            "ok": False,
            "error": "status_marker_count_negative",
        }
    return {
        "ok": True,
        "verification_ok": fields["ok"] == "true",
        "checkpoint_count": checkpoint_count,
        "restored_turn_count": restored_turn_count,
        "verification_error": fields["error"],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify state checkpoint artifacts inside a stateful interactive CLI ZIP.")
    parser.add_argument("zip_path", nargs="?", help="Path to interactive-campaign-results.zip or an uploaded ZIP artifact.")
    parser.add_argument("--summary-path", default="", help="Optional path for writing the structured verification JSON result.")
    parser.add_argument(
        "--aggregate-summary",
        action="append",
        default=[],
        help="Persisted state ZIP verification summary JSON file to include in aggregate mode. Repeat for multiple files.",
    )
    parser.add_argument("--aggregate-path", default="", help="Optional path for writing aggregate verification JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.aggregate_summary:
        aggregate = aggregate_state_zip_verification_summary_files([Path(path) for path in args.aggregate_summary])
        if args.aggregate_path:
            write_state_zip_verification_aggregate(aggregate=aggregate, aggregate_path=Path(args.aggregate_path))
        print(json.dumps(aggregate, indent=2, ensure_ascii=False, sort_keys=True, default=str))
        return 0 if aggregate.get("ok") else 1
    if not args.zip_path:
        raise SystemExit("zip_path is required unless --aggregate-summary is provided")
    result = verify_state_checkpoints_in_zip(Path(args.zip_path))
    if args.summary_path:
        write_state_zip_verification_summary(result=result, summary_path=Path(args.summary_path))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_state_zip_verification_status_marker(result), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
