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

    # Run only JS static analysis (no browser/server needed)
    python run_playwright_tests.py --suite js_analysis

    # Run with headed browser (visible)
    python run_playwright_tests.py --headed

    # Generate report only
    python run_playwright_tests.py --report-only
"""

from __future__ import annotations

import argparse
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
    "frontend": str(TESTS_DIR / "e2e" / "test_frontend.py"),
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

    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "pytest",
        "--rootdir", str(TESTS_DIR),
        "-c", str(TESTS_DIR / "pytest.ini"),
    ]

    # Add test targets
    targets = SUITE_MAP[args.suite]
    cmd.extend(targets.split())

    # Playwright options
    if args.headed:
        cmd.append("--headed")
    if args.slow_mo:
        cmd.extend(["--slowmo", str(args.slow_mo)])

    # Pytest options
    if args.verbose:
        cmd.append("-vv")
    if args.keyword:
        cmd.extend(["-k", args.keyword])

    # Report plugin
    if not args.no_report:
        cmd.extend(["-p", "reports.html_report"])

    print("=" * 70)
    print("  🧪  Omnix Playwright Test Runner")
    print("=" * 70)
    print(f"  Suite  : {args.suite}")
    print(f"  Headed : {args.headed}")
    print(f"  Command: {' '.join(cmd)}")
    print("=" * 70)
    print()

    result = subprocess.run(cmd, cwd=str(TESTS_DIR))

    report_path = TESTS_DIR / "reports" / "report.html"
    if report_path.exists() and not args.no_report:
        print(f"\n📊 HTML Report: {report_path}")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
