"""
End-to-end test for welcome speaker button in header.
Waits for TTS status, clicks button, verifies client handles TTS correctly.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


def test_welcome_speaker_button_e2e(page):
    """Complete end-to-end test for welcome speaker button."""
    console_logs = []
    console_errors = []
    
    # Capture all console output
    def on_console(msg):
        text = msg.text
        console_logs.append(f"[{msg.type}] {text}")
        if msg.type == "error":
            console_errors.append(text)
    
    page.on("console", on_console)
    
    # Navigate to app
    print("Navigating to app...")
    page.goto("http://localhost:5000/", wait_until="domcontentloaded")
    
    # Wait for TTS status to resolve
    print("Waiting for TTS status to complete loading...")
    status_text = page.wait_for_function("""() => {
        const status = document.getElementById('xttsStatusText');
        if (!status) return null;
        const text = status.textContent;
        if (text.includes('Stopped') || text.includes('Running') || 
            text.includes('Ready') || text.includes('Offline') || 
            text.includes('Error')) {
            return text;
        }
        return null;
    }""", timeout=30000)
    
    tts_status = status_text.json_value()
    print(f"TTS status resolved: {tts_status}")
    
    # Verify speaker button exists and is enabled
    speaker_btn = page.locator("#welcomeSpeakerBtn")
    expect(speaker_btn).to_be_visible()
    expect(speaker_btn).to_be_enabled()
    print("Speaker button is visible and enabled")
    
    # Click the speaker button
    print("Clicking welcome speaker button...")
    speaker_btn.click()
    
    # Wait for button to show color state (green/red)
    print("Waiting for button status to update...")
    page.wait_for_function("""() => {
        const btn = document.getElementById('welcomeSpeakerBtn');
        return btn.classList.contains('success') || btn.classList.contains('error');
    }""", timeout=10000)
    
    # Print all console logs
    print("\n--- Console logs during test: ---")
    for log in console_logs:
        print(log)
    
    # Check for critical client errors
    critical_errors = [
        err for err in console_errors 
        if any(term in err.lower() for term in [
            'uncaught', 'typeerror', 'cannot read', 'undefined', 'null'
        ])
    ]
    
    # Verify no uncaught client exceptions
    assert len(critical_errors) == 0, (
        f"Found critical client errors: {critical_errors}\n"
        "Client should handle TTS failures gracefully without exceptions"
    )
    
    # Verify TTS requests were attempted (expected when TTS is running)
    tts_attempts = any(
        '[tts]' in log.lower() or 'api/tts' in log.lower()
        for log in console_logs
    )
    
    if tts_status == 'Running' or tts_status == 'Ready':
        assert tts_attempts, "TTS requests should be made when TTS is running"
        print("✓ TTS requests were successfully initiated")
    
    # Check button state
    button_has_error = page.evaluate("""() => {
        const btn = document.getElementById('welcomeSpeakerBtn');
        return btn.classList.contains('error');
    }""")
    
    button_has_success = page.evaluate("""() => {
        const btn = document.getElementById('welcomeSpeakerBtn');
        return btn.classList.contains('success');
    }""")
    
    print(f"Button state: success={button_has_success}, error={button_has_error}")
    
    # Fail test if button shows error status
    if button_has_error:
        error_logs = [log for log in console_logs if '[error]' in log or '[TTS]' in log or '500' in log]
        error_details = "\n".join(error_logs)
        pytest.fail(f"Speaker button turned red - TTS errors detected\n\n--- TTS ERRORS ---\n{error_details}\n\nButton state: ERROR (red)")
    
    print("\nTest completed successfully:")
    print(f"  - TTS status: {tts_status}")
    print(f"  - Button clicked successfully")
    print(f"  - No critical client errors found ({len(console_errors)} total errors)")
    print(f"  - Button status: {'SUCCESS (green)' if button_has_success else 'NEUTRAL'}")
