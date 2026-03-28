"""
<<<<<<< HEAD
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
=======
Test for JavaScript console errors on the Omnix frontend.
Opens the page and captures all console errors.
"""

import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:5000"


async def check_js_errors():
    """Check for JavaScript errors in the browser console."""
    errors = []
    warnings = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Capture console messages
        def handle_console(msg):
            if msg.type == "error":
                errors.append(msg.text)
            elif msg.type == "warning":
                warnings.append(msg.text)
        
        page.on("console", handle_console)
        
        # Capture page errors
        page_errors = []
        def handle_page_error(err):
            page_errors.append(str(err))
        page.on("pageerror", handle_page_error)
        
        try:
            print(f"Loading {BASE_URL}...")
            response = await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            
            if response.status != 200:
                print(f"ERROR: Page returned status {response.status}")
                await browser.close()
                return False
                
            print("Page loaded, waiting for scripts to execute...")
            await asyncio.sleep(5)  # Wait for all JS to execute
            
            # Check for any critical errors
            print("\n" + "=" * 50)
            print("CONSOLE ERRORS:")
            print("=" * 50)
            
            if errors:
                for e in errors:
                    print(f"  ERROR: {e}")
            else:
                print("  No errors!")
                
            if page_errors:
                print("\nPAGE ERRORS:")
                for e in page_errors:
                    print(f"  {e}")
            
            print("\n" + "=" * 50)
            
            if errors or page_errors:
                print("TEST FAILED - JavaScript errors detected")
                return False
            else:
                print("TEST PASSED - No JavaScript errors")
                return True
                
        except Exception as e:
            print(f"TEST ERROR: {e}")
            return False
        finally:
            await browser.close()


async def main():
    result = await check_js_errors()
    exit(0 if result else 1)


if __name__ == "__main__":
    asyncio.run(main())
>>>>>>> cb63dc998e1562d350c6448678bc91ab0705136f
