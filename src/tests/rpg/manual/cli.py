from __future__ import annotations

import argparse

from tests.rpg.manual import output_artifacts
from tests.rpg.manual.code_diff import write_code_diff_snapshot
from tests.rpg.manual.constants import (
    DEFAULT_CODE_DIFF_ROOTS,
    DEFAULT_MANAGED_SERVER_HEALTH_URLS,
    MANUAL_LOG_MAX_CHUNK_BYTES,
    MANUAL_TEST_TURNS,
    RESULTS_ZIP_PATH,
)
from tests.rpg.manual.managed_servers import ManagedServerGroup
from tests.rpg.manual.output_state import (
    _REGRESSION_WARNING_LOCK,
    _REGRESSION_WARNING_ROWS,
    _REGRESSION_WARNINGS,
)
from tests.rpg.manual.safe import _compact_json
from tests.rpg.manual.threading_helpers import _default_scenario_workers
from tests.rpg.manual.token_usage import write_token_usage_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run manual RPG transcript scenarios.")

    # Keep these flags aligned with the old main().
    parser.add_argument("--session-id", default="manual_test_session")
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run id for generated manual session ids. Defaults to timestamp_uuid.",
    )
    parser.add_argument(
        "--stable-session-ids",
        action="store_true",
        help="Use legacy fixed manual session ids instead of run-scoped fresh ids.",
    )
    parser.add_argument(
        "--no-reset-session-state",
        action="store_true",
        help="Do not delete known saved session artifacts before using a manual session id.",
    )
    parser.add_argument(
        "--scenario-workers",
        type=int,
        default=_default_scenario_workers(),
        help=(
            "Maximum number of service scenarios to run in parallel. "
            "Only turns within each scenario remain sequential. "
            "Default: 8, or env OMNIX_MANUAL_SCENARIO_WORKERS if set."
        ),
    )
    parser.add_argument(
        "--max-log-chunk-bytes",
        type=int,
        default=MANUAL_LOG_MAX_CHUNK_BYTES,
        help="Maximum UTF-8 bytes per manual transcript chunk file. Default: 1000000.",
    )
    parser.add_argument(
        "--no-parallel-scenarios",
        action="store_true",
        help="Run service scenarios sequentially.",
    )
    parser.add_argument(
        "--no-console-llm",
        action="store_true",
        help="Do not print concise readable LLM responses to console.",
    )
    parser.add_argument(
        "--console-llm-raw",
        action="store_true",
        help="Also print raw provider/LLM text in console response logs.",
    )
    parser.add_argument("--no-html-report", action="store_true")
    parser.add_argument("--no-code-diff", action="store_true")
    parser.add_argument(
        "--code-diff-root",
        action="append",
        default=[],
        help=(
            "Root directory to include in code diff snapshot. "
            "Can be passed multiple times. Default: src/, tests/."
        ),
    )
    parser.add_argument("--no-results-zip", action="store_true")
    parser.add_argument("--no-token-usage", action="store_true")
    parser.add_argument(
        "--managed-server-health-url",
        action="append",
        default=[],
        help=(
            "Health URL to wait for after starting managed servers. "
            "Can be passed multiple times. Example: http://127.0.0.1:5101/health"
        ),
    )
    parser.add_argument(
        "--manage-servers",
        action="store_true",
        help="Start and manage external servers before running scenarios.",
    )
    parser.add_argument(
        "--server-command",
        action="append",
        default=[],
        help="Server command to start when --manage-servers is set. Can be passed multiple times.",
    )
    parser.add_argument(
        "--server-startup-timeout",
        type=float,
        default=90.0,
        help="Seconds to wait for server health URLs after starting servers. Default: 90.",
    )
    parser.add_argument("--service-scenarios", action="store_true")
    parser.add_argument(
        "--scenario",
        nargs="*",
        default=[],
        help=(
            "Run only these scenarios. "
            "If not specified, runs all scenarios. "
            "Can be a scenario name prefix, or exact match. "
            "Example: --scenario interaction_l1_l3"
        ),
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--fail-on-regression-warnings",
        action="store_true",
        help="Exit with code 2 if any regression warnings are detected.",
    )
    parser.add_argument(
        "--turn",
        nargs="*",
        default=MANUAL_TEST_TURNS,
        help="Run only these turns within scenarios. Can be turn names or prefixes.",
    )
    parser.add_argument(
        "--single-file",
        action="store_true",
        help="Write all transcripts to a single file instead of splitting into chunks.",
    )
    parser.add_argument(
        "--console-llm-max-chars",
        type=int,
        default=10_000,
        help="Maximum characters to print for LLM responses in console. Default: 10000.",
    )
    parser.add_argument(
        "--artifact-detail",
        choices=["summary", "debug", "full"],
        default="debug",
        help="Artifact detail level: summary (smallest), debug (default, per-scenario JSON), full (deep but bounded).",
    )

    return parser


def _apply_default_args(args: argparse.Namespace) -> argparse.Namespace:
    if not args.code_diff_root:
        args.code_diff_root = list(DEFAULT_CODE_DIFF_ROOTS)

    if not args.managed_server_health_url:
        args.managed_server_health_url = list(DEFAULT_MANAGED_SERVER_HEALTH_URLS)

    if not hasattr(args, "max_log_chunk_bytes"):
        args.max_log_chunk_bytes = MANUAL_LOG_MAX_CHUNK_BYTES

    return args


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = _apply_default_args(parser.parse_args(argv))

    output_artifacts.clear_test_results_root()

    from tests.rpg.manual.runner import run_requested_transcripts

    exit_code = 0

    try:
        with ManagedServerGroup.from_args(args):
            run_requested_transcripts(args)

    except SystemExit:
        raise
    except Exception:
        exit_code = 1
        raise
    finally:
        output_artifacts._write_current_transcript_outputs(
            max_chunk_bytes=max(
                100_000,
                int(getattr(args, "max_log_chunk_bytes", MANUAL_LOG_MAX_CHUNK_BYTES) or MANUAL_LOG_MAX_CHUNK_BYTES),
            )
        )

        if not getattr(args, "no_token_usage", False):
            write_token_usage_report()

        if not getattr(args, "no_code_diff", False):
            write_code_diff_snapshot(roots=getattr(args, "code_diff_root", None))

        if not getattr(args, "no_results_zip", False):
            output_artifacts.write_results_zip(RESULTS_ZIP_PATH)
            output_artifacts._assert_zip_excludes_html(RESULTS_ZIP_PATH)

        with _REGRESSION_WARNING_LOCK:
            warning_rows = list(_REGRESSION_WARNING_ROWS)
            regression_warnings = list(_REGRESSION_WARNINGS)

        if getattr(args, "fail_on_regression_warnings", False):
            if warning_rows:
                print(_compact_json(warning_rows), flush=True)
                raise SystemExit(2)
            if regression_warnings:
                raise SystemExit(
                    "manual regression warnings found:\n"
                    + "\n".join(f"- {warning}" for warning in regression_warnings)
                )

    if exit_code:
        raise SystemExit(exit_code)