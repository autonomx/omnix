# Omnix Playwright Testing Framework

A professional, Playwright-based testing framework for the Omnix AI voice platform. Built with **pytest-playwright**, the **Page Object Model (POM)** pattern, and a custom HTML test report.

## 🏗️ Architecture

```
src/tests/playwright/
├── conftest.py                  # Fixtures, hooks, screenshot-on-failure
├── pytest.ini                   # Pytest configuration
├── pages/                       # Page Object Models
│   ├── base_page.py             # Base class – navigation, waits, assertions
│   ├── chat_page.py             # Chat area interactions
│   ├── sidebar_page.py          # Sidebar navigation
│   ├── header_page.py           # Header status & controls
│   ├── settings_page.py         # Settings modal
│   ├── audiobook_page.py        # Audiobook generator
│   ├── podcast_page.py          # Podcast generator
│   ├── voice_studio_page.py     # Voice Studio TTS
│   ├── voice_clone_page.py      # Voice cloning
│   └── search_page.py           # Search & history modals
├── tests/                       # Test suites
│   ├── test_smoke.py            # UI smoke tests (page load, elements)
│   ├── test_js_console.py       # JavaScript console error detection
│   ├── test_js_variables.py     # JavaScript variable conflict analysis
│   ├── test_frontend.py         # Frontend unit tests (JS evaluation)
│   ├── test_api_endpoints.py    # API endpoint tests (Flask client)
│   ├── test_search.py           # Chat search functionality
│   └── test_healthcheck.py      # API healthcheck validation
├── utils/
│   └── helpers.py               # Shared constants & JS analysis helpers
└── reports/
    ├── html_report.py           # Custom HTML report generator plugin
    └── .gitignore               # Exclude generated artifacts
```

## 🚀 Quick Start

### Prerequisites

```bash
pip install playwright pytest-playwright
python -m playwright install chromium
```

### Run All Tests

```bash
python run_playwright_tests.py
```

### Run Specific Suites

```bash
# Smoke tests (UI element checks)
python run_playwright_tests.py --suite smoke

# API tests (Flask test client, no browser needed)
python run_playwright_tests.py --suite api

# Frontend JS unit tests (browser-evaluated)
python run_playwright_tests.py --suite frontend

# JS static analysis (no browser/server needed)
python run_playwright_tests.py --suite js_analysis

# Console error detection
python run_playwright_tests.py --suite console
```

### Run With Options

```bash
# Headed browser (visible)
python run_playwright_tests.py --headed

# Slow motion for debugging
python run_playwright_tests.py --headed --slow-mo 500

# Run specific tests by keyword
python run_playwright_tests.py -k "test_token"

# Skip HTML report
python run_playwright_tests.py --no-report

# Extra verbose
python run_playwright_tests.py --verbose
```

### Run Directly With pytest

```bash
cd src/tests/playwright

# All tests
python -m pytest tests/ -v --rootdir . -c pytest.ini

# Single file
python -m pytest tests/test_smoke.py -v --rootdir . -c pytest.ini

# With custom report
python -m pytest tests/ -v --rootdir . -c pytest.ini -p reports.html_report
```

## 📊 Custom HTML Report

A professional HTML report is auto-generated at `src/tests/playwright/reports/report.html`:

- **Executive summary** with pass/fail/skip counts
- **Animated donut chart** showing pass rate percentage
- **Collapsible test suites** organized by class
- **Search & filter** bar – filter by outcome or search by name
- **Failure details** with stack traces and inline screenshots
- **Timing data** per test
- **Auto-expands** failed suites

## 🧩 Page Object Model

All UI interactions are encapsulated in Page Objects under `pages/`. Each page object:

- Inherits from `BasePage` with shared utilities
- Defines element selectors as class constants
- Provides action methods (click, fill, type)
- Includes built-in assertion methods using Playwright's `expect`

### Example Usage

```python
def test_send_message(self, chat_page: ChatPage):
    chat_page.open()
    chat_page.type_message("Hello, AI!")
    chat_page.send_button.click()
    chat_page.expect_typing_visible()
    chat_page.expect_typing_hidden(timeout=30_000)
    assert chat_page.get_message_count() >= 2
```

### Available Page Objects

| Page Object       | Covers                                      |
| ----------------- | ------------------------------------------- |
| `BasePage`        | Navigation, waits, assertions, screenshots  |
| `ChatPage`        | Message input, send, clear, voice toggle    |
| `SidebarPage`     | Navigation buttons, expand/collapse         |
| `HeaderPage`      | Status dots, model select, theme toggle     |
| `SettingsPage`    | Provider config, system prompts, VAD        |
| `AudiobookPage`   | Text input, analyze, generate, library      |
| `PodcastPage`     | Episode setup, speakers, generate           |
| `VoiceStudioPage` | TTS with emotion/speed/pitch controls       |
| `VoiceClonePage`  | Record/upload tabs, save voice              |
| `SearchPage`      | Search modal, history modal                 |

## 🧪 Test Suites

| Suite               | File                     | Tests | Needs Server? |
| ------------------- | ------------------------ | ----- | ------------- |
| Smoke Tests         | `test_smoke.py`          | 24    | ✅ Yes        |
| JS Console Errors   | `test_js_console.py`     | 3     | ✅ Yes        |
| Frontend Unit Tests | `test_frontend.py`       | 30    | ✅ Yes        |
| JS Variable Analysis| `test_js_variables.py`   | 4     | ❌ No         |
| API Endpoints       | `test_api_endpoints.py`  | 9     | ❌ No (Flask) |
| Search              | `test_search.py`         | 14    | ❌ No (Flask) |
| Healthcheck         | `test_healthcheck.py`    | 12    | ❌ No (Flask) |

## 🔧 Fixtures

| Fixture              | Scope    | Description                               |
| -------------------- | -------- | ----------------------------------------- |
| `page`               | function | Playwright browser page (from pytest-playwright) |
| `chat_page`          | function | ChatPage instance                         |
| `sidebar_page`       | function | SidebarPage instance                      |
| `header_page`        | function | HeaderPage instance                       |
| `settings_page`      | function | SettingsPage instance                     |
| `audiobook_page`     | function | AudiobookPage instance                    |
| `podcast_page`       | function | PodcastPage instance                      |
| `voice_studio_page`  | function | VoiceStudioPage instance                  |
| `voice_clone_page`   | function | VoiceClonePage instance                   |
| `search_page`        | function | SearchPage instance                       |
| `flask_app`          | session  | Flask test application                    |
| `flask_client`       | session  | Flask test client                         |
| `api_context`        | session  | Playwright API request context            |
| `mock_llm_response`  | function | Mock LLM API response                     |
| `mock_tts_response`  | function | Mock TTS API response                     |
| `mock_stt_response`  | function | Mock STT API response                     |

## 📸 Screenshots on Failure

When any browser test fails, a full-page screenshot is automatically captured and:
- Saved to `reports/screenshots/FAIL_<test_name>_<timestamp>.png`
- Embedded inline (base64) in the HTML report
