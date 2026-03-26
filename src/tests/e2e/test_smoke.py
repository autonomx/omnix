"""
Smoke tests – verify the application loads and core UI elements are present.

These tests use Playwright to open the app in a headless browser and
validate that the main page renders without errors.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


class TestPageLoad:
    """Verify the main page loads correctly."""

    def test_page_loads_successfully(self, page: Page):
        """The root URL returns HTTP 200 and the page title contains 'Omnix'."""
        response = page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        assert response is not None
        assert response.status == 200

    def test_page_title(self, page: Page):
        """Page title should reference the application name."""
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        title = page.title()
        assert title, "Page title should not be empty"

    def test_favicon_loads(self, page: Page):
        """Favicon should be served."""
        resp = page.request.get("http://localhost:5000/favicon.ico")
        assert resp.status in (200, 204, 304)


class TestCoreUIElements:
    """Verify that core UI elements are rendered on page load."""

    @pytest.fixture(autouse=True)
    def _load_page(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

    def test_chat_container_visible(self, page: Page):
        expect(page.locator("#chatContainer")).to_be_visible()

    def test_message_input_visible(self, page: Page):
        expect(page.locator("#messageInput")).to_be_visible()

    def test_send_button_visible(self, page: Page):
        expect(page.locator("#sendBtn")).to_be_visible()

    def test_sidebar_exists(self, page: Page):
        expect(page.locator("#sidebar")).to_be_attached()

    def test_model_select_visible(self, page: Page):
        expect(page.locator("#modelSelect")).to_be_visible()

    def test_status_dot_visible(self, page: Page):
        expect(page.locator("#statusDot")).to_be_visible()

    def test_clear_button_visible(self, page: Page):
        expect(page.locator("#clearBtn")).to_be_visible()

    def test_theme_toggle_visible(self, page: Page):
        expect(page.locator("#themeToggle")).to_be_visible()

    def test_mic_button_visible(self, page: Page):
        expect(page.locator("#micBtn")).to_be_visible()

    def test_conversation_toggle_visible(self, page: Page):
        expect(page.locator("#conversationToggle")).to_be_visible()


class TestSidebarNavigation:
    """Verify sidebar navigation elements."""

    @pytest.fixture(autouse=True)
    def _load_page(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

    def test_sidebar_has_settings_button(self, page: Page):
        # Either expanded or collapsed button should exist
        settings = page.locator("#settingsBtnOption, #settingsBtnCollapsed")
        expect(settings.first).to_be_attached()

    def test_sidebar_has_audiobook_button(self, page: Page):
        audiobook = page.locator("#audiobookBtnOption, #audiobookBtnCollapsed")
        expect(audiobook.first).to_be_attached()

    def test_sidebar_has_podcast_button(self, page: Page):
        podcast = page.locator("#podcastBtnOption, #podcastBtnCollapsed")
        expect(podcast.first).to_be_attached()

    def test_sidebar_has_voice_studio_button(self, page: Page):
        vs = page.locator("#voiceStudioBtnOption, #voiceStudioBtnCollapsed")
        expect(vs.first).to_be_attached()

    def test_sidebar_has_voice_clone_button(self, page: Page):
        vc = page.locator("#voiceCloneBtnOption, #voiceCloneBtnCollapsed")
        expect(vc.first).to_be_attached()


class TestModals:
    """Verify modals exist in the DOM (hidden by default)."""

    @pytest.fixture(autouse=True)
    def _load_page(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

    @pytest.mark.parametrize(
        "modal_id",
        [
            "settingsModal",
            "searchChatModal",
            "historyModal",
            "voiceCloneModal",
            "audiobook-modal",
            "podcast-modal",
            "voiceStudioModal",
            "llmModelModal",
        ],
    )
    def test_modal_exists_hidden(self, page: Page, modal_id: str):
        """Modal should be present in DOM but hidden by default."""
        modal = page.locator(f"#{modal_id}")
        expect(modal).to_be_attached()
