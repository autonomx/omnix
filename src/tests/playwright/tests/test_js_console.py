"""
JavaScript console error tests – migrated from test_js_console.py.

Uses Playwright to load the application page and capture any JavaScript
console errors or uncaught page errors.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page


class TestJSConsoleErrors:
    """Detect JavaScript errors in the browser console."""

    def test_no_js_console_errors(self, page: Page):
        """Page should load without any JavaScript console errors."""
        errors: list[str] = []
        page_errors: list[str] = []

        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        response = page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        assert response is not None and response.status == 200, (
            f"Page failed to load (status={getattr(response, 'status', 'N/A')})"
        )

        # Allow scripts time to execute
        page.wait_for_timeout(5000)

        all_errors = errors + page_errors
        assert len(all_errors) == 0, (
            f"JavaScript errors detected:\n" + "\n".join(f"  • {e}" for e in all_errors)
        )

    def test_no_js_page_errors(self, page: Page):
        """No uncaught exceptions should be thrown."""
        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        assert len(page_errors) == 0, (
            f"Uncaught page errors:\n" + "\n".join(f"  • {e}" for e in page_errors)
        )

    def test_no_js_warnings(self, page: Page):
        """Page should ideally load without console warnings (non-blocking)."""
        warnings: list[str] = []
        page.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)

        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # This is informational – we log warnings but don't fail
        if warnings:
            print(f"\n⚠️  Console warnings ({len(warnings)}):")
            for w in warnings[:10]:
                print(f"    {w}")
