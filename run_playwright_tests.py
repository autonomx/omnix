#!/usr/bin/env python3
"""
Omnix Playwright Test Runner

Run the full Playwright-based test suite with custom HTML report generation.

Usage:
    # Run all tests
    python run_playwright_tests.py

    # Run only smoke tests
    python run_playwright_tests.py --suite smoke

    # Run only API tests (no browser needed)
    python run_playwright_tests.py --suite api

    # Run only frontend JS tests
    python run_playwright_tests.py --suite frontend

    # Run the Live Voice test with Windows speech synthesis
    python run_playwright_tests.py --suite live_voice --headed --no-report

    # Run the Live Voice test with a specific MP3 or WAV
    python run_playwright_tests.py --suite live_voice --headed --no-report --live-voice-audio hows-it-going.mp3

    # Run the five-turn Live Voice API test without a browser
    python run_playwright_tests.py --suite live_voice_api --no-report

    # Run only JS static analysis (no browser/server needed)
    python run_playwright_tests.py --suite js_analysis

    # Run with headed browser (visible)
    python run_playwright_tests.py --headed
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent / "src" / "tests"

SUITE_MAP = {
    "all": " ".join([
        str(TESTS_DIR / "e2e"),
        str(TESTS_DIR / "api"),
        str(TESTS_DIR / "integration"),
    ]),
    "smoke": str(TESTS_DIR / "e2e" / "test_smoke.py"),
    "api": " ".join([
        str(TESTS_DIR / "api" / "sanity" / "test_api_endpoints.py"),
        str(TESTS_DIR / "api" / "regression" / "test_search_api.py"),
        str(TESTS_DIR / "api" / "healthcheck" / "test_health_responses.py"),
    ]),
    "healthcheck": str(TESTS_DIR / "api" / "healthcheck" / "test_health_responses.py"),
    "frontend": str(TESTS_DIR / "e2e" / "test_frontend.py"),
    "live_voice": str(TESTS_DIR / "e2e" / "test_live_voice_audio.py"),
    "live_voice_api": str(TESTS_DIR / "e2e" / "test_live_voice_api.py"),
    "js_analysis": str(TESTS_DIR / "e2e" / "test_js_variables.py"),
    "console": str(TESTS_DIR / "e2e" / "test_js_console.py"),
}


def main():
    parser = argparse.ArgumentParser(description="Omnix Playwright Test Runner")
    parser.add_argument(
        "--suite",
        choices=list(SUITE_MAP.keys()),
        default="all",
        help="Which test suite to run (default: all)",
    )
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--slow-mo", type=int, default=0, help="Slow down browser operations (ms)")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers")
    parser.add_argument("-k", "--keyword", type=str, help="Only run tests matching keyword expression")
    parser.add_argument("--no-report", action="store_true", help="Skip HTML report generation")
    parser.add_argument("--verbose", action="store_true", help="Extra verbose output")
    parser.add_argument(
        "--live-voice-audio",
        type=str,
        help="MP3 or WAV file to inject as the Live Voice microphone source",
    )
    parser.add_argument(
        "--app-url",
        type=str,
        help="Override the Live Voice web app URL (default: http://127.0.0.1:5173)",
    )
    parser.add_argument(
        "--stt-url",
        type=str,
        help="Override the Parakeet STT URL (default: http://127.0.0.1:5201)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        help="Override the Live Voice API gateway URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--api-stt-url",
        type=str,
        help="Override the Live Voice API STT URL (default: http://127.0.0.1:5201)",
    )

    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "pytest",
        "--rootdir", str(TESTS_DIR),
        "-c", str(TESTS_DIR / "pytest.ini"),
    ]

    targets = SUITE_MAP[args.suite]
    cmd.extend(targets.split())

    if args.headed:
        cmd.append("--headed")
    if args.slow_mo:
        cmd.extend(["--slowmo", str(args.slow_mo)])

    if args.verbose:
        cmd.append("-vv")
    if args.suite == "live_voice_api":
        # The protocol trace is intentionally printed live for this long-running suite.
        cmd.append("-s")
    if args.keyword:
        cmd.extend(["-k", args.keyword])

    if not args.no_report:
        cmd.extend(["-p", "reports.html_report"])

    run_env = os.environ.copy()
    if args.suite == "live_voice":
        run_env["OMNIX_RUN_LIVE_VOICE_AUDIO"] = "1"
        run_env.setdefault("OMNIX_BASE_URL", "http://127.0.0.1:5173")
        run_env.setdefault("OMNIX_STT_URL", "http://127.0.0.1:5201")
    if args.suite == "live_voice_api":
        run_env["OMNIX_RUN_LIVE_VOICE_API"] = "1"
        run_env.setdefault("OMNIX_LIVE_VOICE_API_URL", "http://127.0.0.1:8000")
        run_env.setdefault("OMNIX_LIVE_VOICE_API_STT_URL", "http://127.0.0.1:5201")
    if args.live_voice_audio:
        run_env["OMNIX_LIVE_VOICE_AUDIO"] = str(Path(args.live_voice_audio).expanduser().resolve())
    if args.app_url:
        run_env["OMNIX_BASE_URL"] = args.app_url
    if args.stt_url:
        run_env["OMNIX_STT_URL"] = args.stt_url
    if args.api_url:
        run_env["OMNIX_LIVE_VOICE_API_URL"] = args.api_url
    if args.api_stt_url:
        run_env["OMNIX_LIVE_VOICE_API_STT_URL"] = args.api_stt_url

    print("=" * 70)
    print("  🧪  Omnix Playwright Test Runner")
    print("=" * 70)
    print(f"  Suite  : {args.suite}")
    print(f"  Headed : {args.headed}")
    if args.suite == "live_voice":
        print(f"  App    : {run_env['OMNIX_BASE_URL']}")
        print(f"  STT    : {run_env['OMNIX_STT_URL']}")
        print(f"  Audio  : {run_env.get('OMNIX_LIVE_VOICE_AUDIO', 'Windows System.Speech')}")
    if args.suite == "live_voice_api":
        print(f"  API    : {run_env['OMNIX_LIVE_VOICE_API_URL']}")
        print(f"  STT    : {run_env['OMNIX_LIVE_VOICE_API_STT_URL']}")
    print(f"  Command: {' '.join(cmd)}")
    print("=" * 70)
    print()

    result = subprocess.run(cmd, cwd=str(TESTS_DIR), env=run_env)

    report_path = TESTS_DIR / "reports" / "report.html"
    if report_path.exists() and not args.no_report:
        print(f"\n📊 HTML Report: {report_path}")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
