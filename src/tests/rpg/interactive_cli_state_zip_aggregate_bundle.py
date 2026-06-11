"""Phase 13.90 — all-in-one bundle for state ZIP aggregate verifier artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_cli_state_zip_aggregate_verify as aggregate_verify  # noqa: E402
from tests.rpg import interactive_cli_state_zip_verify as verify_cli  # noqa: E402

STATE_ZIP_AGGREGATE_ALL_BUNDLE_VERSION = "interactive_cli_state_zip_aggregate_all_bundle_v1"
STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST = "state-zip-aggregate-bundle-manifest.json"
STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE = "state-zip-aggregate.json"
STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER = "state-zip-aggregate-read-status-marker.txt"
STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY = "state-zip-aggregate-read-bundle-summary.json"


def _json_bytes(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str)


def build_state_zip_aggregate_all_bundle_manifest(
    *,
    aggregate_payload: Mapping[str, Any],
    status_marker: str,
    bundle_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic manifest for an all-in-one aggregate artifact bundle."""

    return {
        "format_version": STATE_ZIP_AGGREGATE_ALL_BUNDLE_VERSION,
        "aggregate_entry": STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE,
        "status_marker_entry": STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER,
        "bundle_summary_entry": STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY,
        "aggregate_format_version": aggregate_payload.get("aggregate_format_version"),
        "aggregate_ok": bool(aggregate_payload.get("ok")),
        "summary_count": int(aggregate_payload.get("summary_count") or 0),
        "failed": int(aggregate_payload.get("failed") or 0),
        "status_marker": str(status_marker),
        "bundle_summary_ok": bool(bundle_summary.get("ok")),
        "entries": [
            STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST,
            STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE,
            STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER,
            STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY,
        ],
    }


def write_state_zip_aggregate_all_bundle(
    *,
    aggregate_path: str | Path,
    bundle_zip_path: str | Path,
    status_marker: str | None = None,
) -> dict[str, Any]:
    """Create one ZIP containing the aggregate, read marker, bundle summary, and manifest."""

    read_result = aggregate_verify.read_state_zip_verification_aggregate(aggregate_path)
    if not read_result.get("ok"):
        return {
            "ok": False,
            "error": "aggregate_read_failed",
            "read_result": read_result,
        }

    marker = status_marker or aggregate_verify.render_state_zip_verification_aggregate_read_status_marker(read_result)
    bundle_summary = aggregate_verify.verify_state_zip_aggregate_read_artifact_bundle(
        aggregate_path=aggregate_path,
        status_marker=marker,
    )
    if not bundle_summary.get("ok"):
        return {
            "ok": False,
            "error": "aggregate_bundle_verification_failed",
            "bundle_summary": bundle_summary,
        }

    aggregate_payload = read_result.get("aggregate") if isinstance(read_result.get("aggregate"), Mapping) else {}
    manifest = build_state_zip_aggregate_all_bundle_manifest(
        aggregate_payload=aggregate_payload,
        status_marker=marker,
        bundle_summary=bundle_summary,
    )
    bundle_path = Path(bundle_zip_path)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST, _json_bytes(manifest))
        archive.writestr(STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE, _json_bytes(aggregate_payload))
        archive.writestr(STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER, marker)
        archive.writestr(STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY, _json_bytes(bundle_summary))

    return {
        "ok": True,
        "bundle_path": str(bundle_path),
        "manifest": manifest,
        "bundle_summary": bundle_summary,
    }


def verify_state_zip_aggregate_all_bundle(bundle_zip_path: str | Path) -> dict[str, Any]:
    """Verify an all-in-one aggregate bundle ZIP and its internal artifact agreement."""

    path = Path(bundle_zip_path)
    if not path.exists():
        return {
            "ok": False,
            "error": "aggregate_all_bundle_missing",
            "path": str(path),
        }
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            required = {
                STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST,
                STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE,
                STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER,
                STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY,
            }
            missing = sorted(required.difference(names))
            if missing:
                return {
                    "ok": False,
                    "error": "aggregate_all_bundle_entries_missing",
                    "path": str(path),
                    "missing_entries": missing,
                }
            manifest = json.loads(archive.read(STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST).decode("utf-8"))
            aggregate_payload = json.loads(archive.read(STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE).decode("utf-8"))
            marker = archive.read(STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER).decode("utf-8")
            bundle_summary = json.loads(archive.read(STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY).decode("utf-8"))
    except zipfile.BadZipFile:
        return {
            "ok": False,
            "error": "aggregate_all_bundle_zip_invalid",
            "path": str(path),
        }
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {
            "ok": False,
            "error": "aggregate_all_bundle_payload_invalid",
            "path": str(path),
            "message": str(exc),
        }

    if not isinstance(manifest, dict) or manifest.get("format_version") != STATE_ZIP_AGGREGATE_ALL_BUNDLE_VERSION:
        return {
            "ok": False,
            "error": "aggregate_all_bundle_manifest_invalid",
            "path": str(path),
            "manifest": manifest,
        }
    if not isinstance(aggregate_payload, dict) or not isinstance(bundle_summary, dict):
        return {
            "ok": False,
            "error": "aggregate_all_bundle_payload_not_object",
            "path": str(path),
        }
    aggregate_validation = aggregate_verify.validate_state_zip_verification_aggregate_payload(aggregate_payload)
    marker_result = aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker(marker)
    if not aggregate_validation.get("ok"):
        return {
            "ok": False,
            "error": "aggregate_all_bundle_aggregate_invalid",
            "path": str(path),
            "validation": aggregate_validation,
        }
    if not marker_result.get("ok"):
        return {
            "ok": False,
            "error": "aggregate_all_bundle_marker_invalid",
            "path": str(path),
            "marker_result": marker_result,
        }
    expected_manifest = build_state_zip_aggregate_all_bundle_manifest(
        aggregate_payload=aggregate_payload,
        status_marker=marker,
        bundle_summary=bundle_summary,
    )
    if manifest != expected_manifest:
        return {
            "ok": False,
            "error": "aggregate_all_bundle_manifest_mismatch",
            "path": str(path),
            "expected_manifest": expected_manifest,
            "actual_manifest": manifest,
        }
    if not bool(bundle_summary.get("ok")):
        return {
            "ok": False,
            "error": "aggregate_all_bundle_summary_not_ok",
            "path": str(path),
            "bundle_summary": bundle_summary,
        }
    return {
        "ok": True,
        "path": str(path),
        "manifest": manifest,
        "aggregate": aggregate_payload,
        "marker_result": marker_result,
        "bundle_summary": bundle_summary,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write or verify all-in-one state ZIP aggregate bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write", help="Create an all-in-one aggregate bundle ZIP.")
    write_parser.add_argument("aggregate_path", help="Path to a persisted state ZIP aggregate JSON artifact.")
    write_parser.add_argument("bundle_zip_path", help="Path where the all-in-one aggregate bundle ZIP should be written.")
    write_parser.add_argument(
        "--status-marker",
        default="",
        help="Optional aggregate-read status marker. When omitted, a marker is rendered from the aggregate JSON.",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify an all-in-one aggregate bundle ZIP.")
    verify_parser.add_argument("bundle_zip_path", help="Path to the all-in-one aggregate bundle ZIP to verify.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.command == "write":
        result = write_state_zip_aggregate_all_bundle(
            aggregate_path=Path(args.aggregate_path),
            bundle_zip_path=Path(args.bundle_zip_path),
            status_marker=args.status_marker or None,
        )
    else:
        result = verify_state_zip_aggregate_all_bundle(Path(args.bundle_zip_path))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
