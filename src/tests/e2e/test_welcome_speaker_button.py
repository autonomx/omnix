"""
Test for welcome speaker button in header.
Verifies that clicking the speaker button triggers TTS functionality
and checks for console errors.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


class TestWelcomeSpeakerButton:
    """Test suite for welcome speaker button functionality."""

    def test_welcome_speaker_button_exists(self, page: Page):
        """Verify the speaker button is present in the header."""
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        
        # Verify button exists
        speaker_btn = page.locator("#welcomeSpeakerBtn")
        expect(speaker_btn).to_be_visible()
        expect(speaker_btn).to_be_enabled()
        
        # Verify button has correct title
        expect(speaker_btn).to_have_attribute("title", "Play welcome message")

    def test_clicking_speaker_button_triggers_tts(self, page: Page):
        """Test clicking the speaker button and monitor for TTS errors."""
        console_errors = []
        
        # Capture console errors
        def on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
        
        page.on("console", on_console)
        
        # Navigate to app
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        
        # Wait for all scripts to load
        page.wait_for_function("""() => {
            return typeof window.speakText !== 'undefined' || 
                   typeof window.speakTextStreaming !== 'undefined';
        }""", timeout=5000)
        
        # Click the speaker button
        speaker_btn = page.locator("#welcomeSpeakerBtn")
        speaker_btn.click()
        
        # Wait briefly for any errors to appear
        page.wait_for_timeout(1000)
        
        # Verify no TTS related console errors
        tts_errors = [
            err for err in console_errors 
            if any(term in err.lower() for term in [
                'tts', 'speak', 'audio', 'voice', 'sound',
                'networkerror', 'fetch', 'api/tts'
            ])
        ]
        
        assert len(tts_errors) == 0, f"Found TTS related console errors: {tts_errors}"

    def test_speak_function_available(self, page: Page):
        """Verify speakText function is available globally."""
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        
        page.wait_for_function("""() => {
            return typeof window.speakText === 'function' || 
                   typeof window.speakTextStreaming === 'function';
        }""", timeout=5000)
        
        # Verify function exists
        has_speak_function = page.evaluate("""() => {
            return typeof window.speakText === 'function' || 
                   typeof window.speakTextStreaming === 'function';
        }""")
        
        assert has_speak_function, "Speak function not available on window object"

    def test_click_calls_speak_function(self, page: Page):
        """Verify button click invokes the speak function with correct text."""
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        
        # Wait for chat module to initialize
        page.wait_for_function("""() => {
            return document.getElementById('welcomeSpeakerBtn') !== null &&
                   typeof window.speakText === 'function';
        }""", timeout=5000)
        
        # Spy on speak function
        page.evaluate("""() => {
            window.originalSpeakText = window.speakText;
            window.speakTextCalled = false;
            window.speakTextArgument = null;
            
            window.speakText = function(text, speaker) {
                window.speakTextCalled = true;
                window.speakTextArgument = text;
                return Promise.resolve();
            };
        }""")
        
        # Click button
        page.locator("#welcomeSpeakerBtn").click()
        page.wait_for_timeout(100)
        
        # Verify function was called
        called = page.evaluate("() => window.speakTextCalled")
        arg = page.evaluate("() => window.speakTextArgument")
        
        assert called is True, "speakText was not called when clicking speaker button"
        assert arg == "Hello, welcome to Omnix chat", f"Unexpected text passed to speakText: {arg}"
        
        # Restore original function
        page.evaluate("() => window.speakText = window.originalSpeakText")
