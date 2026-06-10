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
    print(render_state_zip_verification_status_marker(result), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
