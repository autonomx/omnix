"""
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
