"""
Pytest configuration and fixtures for Omnix Playwright tests.

Provides page-object fixtures, API request context, Flask test client,
console-error capture, and automatic screenshot-on-failure.
"""

from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone

import pytest
from playwright.sync_api import Page, APIRequestContext, BrowserContext

# Add project roots to path for importing app modules
SRC_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SRC_DIR.parent
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(TESTS_DIR))

# ---------------------------------------------------------------------------
# Page-object imports
# ---------------------------------------------------------------------------
from pages.base_page import BasePage
from pages.chat_page import ChatPage
from pages.sidebar_page import SidebarPage
from pages.header_page import HeaderPage
from pages.settings_page import SettingsPage
from pages.audiobook_page import AudiobookPage
from pages.podcast_page import PodcastPage
from pages.voice_studio_page import VoiceStudioPage
from pages.voice_clone_page import VoiceClonePage
from pages.search_page import SearchPage

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("OMNIX_BASE_URL", "http://localhost:5000")
SCREENSHOTS_DIR = Path(__file__).parent / "reports" / "screenshots"

# ---------------------------------------------------------------------------
# Pytest options
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--base-url-omnix",
        action="store",
        default=BASE_URL,
        help="Base URL for the running Omnix application",
    )


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_url(request):
    """Resolved base URL."""
    return request.config.getoption("--base-url-omnix")


@pytest.fixture(scope="session")
def flask_app():
    """Create a Flask test application (for API-only tests that don't need a browser)."""
    try:
        from app import create_app

        flask_app = create_app()
        flask_app.config["TESTING"] = True
        yield flask_app
    except ImportError:
        pytest.skip("Flask app could not be imported – skipping API tests")


@pytest.fixture(scope="session")
def flask_client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


# ---------------------------------------------------------------------------
# Page-object fixtures (function-scoped – fresh per test)
# ---------------------------------------------------------------------------

@pytest.fixture
def base_page(page: Page) -> BasePage:
    return BasePage(page)


@pytest.fixture
def chat_page(page: Page) -> ChatPage:
    return ChatPage(page)


@pytest.fixture
def sidebar_page(page: Page) -> SidebarPage:
    return SidebarPage(page)


@pytest.fixture
def header_page(page: Page) -> HeaderPage:
    return HeaderPage(page)


@pytest.fixture
def settings_page(page: Page) -> SettingsPage:
    return SettingsPage(page)


@pytest.fixture
def audiobook_page(page: Page) -> AudiobookPage:
    return AudiobookPage(page)


@pytest.fixture
def podcast_page(page: Page) -> PodcastPage:
    return PodcastPage(page)


@pytest.fixture
def voice_studio_page(page: Page) -> VoiceStudioPage:
    return VoiceStudioPage(page)


@pytest.fixture
def voice_clone_page(page: Page) -> VoiceClonePage:
    return VoiceClonePage(page)


@pytest.fixture
def search_page(page: Page) -> SearchPage:
    return SearchPage(page)


# ---------------------------------------------------------------------------
# Playwright API request context fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_context(playwright):
    """Playwright APIRequestContext for headless API testing."""
    ctx = playwright.request.new_context(base_url=BASE_URL)
    yield ctx
    ctx.dispose()


# ---------------------------------------------------------------------------
# Mock data fixtures (shared with old tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm_response():
    return {
        "choices": [
            {
                "message": {"content": "Hello! This is a test response from the AI."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


@pytest.fixture
def mock_tts_response():
    import base64

    wav_data = b"RIFF" + (44).to_bytes(4, "little") + b"WAVE"
    return {
        "success": True,
        "audio": base64.b64encode(wav_data).decode("utf-8"),
        "sample_rate": 24000,
    }


@pytest.fixture
def mock_stt_response():
    return {
        "success": True,
        "segments": [{"text": "Hello world", "start": 0.0, "end": 1.0}],
        "duration": 1.5,
    }


@pytest.fixture
def sample_session_data():
    return {
        "title": "Test Chat",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        "system_prompt": "You are a helpful assistant.",
    }


@pytest.fixture
def sample_audiobook_text():
    return """
    Narrator: The sun was setting over the hills.
    Sofia: What a beautiful evening!
    Morgan: Indeed, it reminds me of home.

    They walked together along the path, enjoying the peaceful moment.

    Sofia: I wish moments like this could last forever.
    """


# ---------------------------------------------------------------------------
# Automatic screenshot on failure
# ---------------------------------------------------------------------------

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Take a screenshot when a browser test fails."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        page: Page | None = item.funcargs.get("page")
        if page is not None:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_name = item.name.replace("[", "_").replace("]", "")
            screenshot_path = SCREENSHOTS_DIR / f"FAIL_{safe_name}_{ts}.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                if hasattr(report, "extra"):
                    report.extra = getattr(report, "extra", [])
                # Attach path as user property for the custom report
                item.user_properties.append(("screenshot", str(screenshot_path)))
            except Exception:
                pass  # browser may already be closed


# ---------------------------------------------------------------------------
# JS static analysis helpers (used by test_js_variables)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def static_dir():
    return SRC_DIR / "static"


@pytest.fixture(scope="session")
def js_files(static_dir):
    """Collect all JavaScript files in the static directory."""
    files = []
    for root, _, filenames in os.walk(static_dir):
        for f in filenames:
            if f.endswith(".js"):
                files.append(Path(root) / f)
    return files
