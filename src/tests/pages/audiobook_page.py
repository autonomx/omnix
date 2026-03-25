"""
Audiobook Page Object – audiobook generation and playback.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from .base_page import BasePage


class AudiobookPage(BasePage):
    """Page Object for the Audiobook modal."""

    MODAL = "#audiobook-modal"
    FILE_INPUT = "#audiobook-file"
    TEXT_INPUT = "#audiobook-text"
    ANALYZE_BTN = "#audiobook-analyze-btn"
    AI_STRUCTURE_BTN = "#audiobook-ai-structure-btn"
    DIRECT_BTN = "#audiobook-direct-btn"
    SPEAKERS_SECTION = "#audiobook-speakers-section"
    SPEAKERS_LIST = "#audiobook-speakers-list"
    VOICE_PANEL = "#audiobook-voice-panel"
    VOICE_PANEL_LIST = "#audiobook-voice-panel-list"
    PROGRESS = "#audiobook-progress"
    PROGRESS_BAR = "#audiobook-progress-bar"
    PROGRESS_TEXT = "#audiobook-progress-text"
    PLAYER = "#audiobook-player"
    LIBRARY_SECTION = "#audiobook-library-section"
    LIBRARY_LIST = "#audiobook-library-list"

    def __init__(self, page: Page) -> None:
        super().__init__(page)

    # ------------------------------------------------------------------
    # Modal management
    # ------------------------------------------------------------------

    def is_open(self) -> bool:
        return self.locator(self.MODAL).is_visible()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        self.by_id("audiobook-text").fill(text)

    def get_text(self) -> str:
        return self.by_id("audiobook-text").input_value()

    def upload_file(self, file_path: str) -> None:
        self.by_id("audiobook-file").set_input_files(file_path)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def click_analyze(self) -> None:
        self.by_id("audiobook-analyze-btn").click()

    def click_ai_structure(self) -> None:
        self.by_id("audiobook-ai-structure-btn").click()

    def click_direct_generate(self) -> None:
        self.by_id("audiobook-direct-btn").click()

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def get_progress_text(self) -> str:
        return self.by_id("audiobook-progress-text").inner_text()

    def is_progress_visible(self) -> bool:
        return self.by_id("audiobook-progress").is_visible()

    # ------------------------------------------------------------------
    # Library
    # ------------------------------------------------------------------

    def get_library_count(self) -> int:
        return self.by_id("audiobook-library-list").locator("> *").count()

    # ------------------------------------------------------------------
    # Assertions
    # ------------------------------------------------------------------

    def expect_open(self) -> None:
        expect(self.locator(self.MODAL)).to_be_visible()

    def expect_closed(self) -> None:
        expect(self.locator(self.MODAL)).to_be_hidden()

    def expect_speakers_visible(self) -> None:
        expect(self.by_id("audiobook-speakers-section")).to_be_visible()
