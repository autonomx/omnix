<<<<<<< HEAD
# Omnix Playwright Testing Framework

A professional, Playwright-based testing framework for the Omnix AI voice platform. Built with **pytest-playwright**, the **Page Object Model (POM)** pattern, and a custom HTML test report.
=======
# Test Suite for Omnix

This directory contains comprehensive tests for the Omnix application.
>>>>>>> cb63dc998e1562d350c6448678bc91ab0705136f

## 🏗️ Architecture

```
src/tests/
<<<<<<< HEAD
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
├── e2e/                         # End-to-end Playwright browser tests
│   ├── test_smoke.py            # UI smoke tests (page load, elements)
│   ├── test_frontend.py         # Frontend unit tests (JS evaluation)
│   ├── test_js_console.py       # JavaScript console error detection
│   └── test_js_variables.py     # JavaScript variable conflict analysis
├── api/                         # Backend API tests
│   ├── healthcheck/
│   │   └── test_health_responses.py  # API healthcheck validation
│   ├── sanity/
│   │   └── test_api_endpoints.py     # API endpoint tests (Flask client)
│   └── regression/
│       └── test_search_api.py        # Chat search functionality
├── integration/                 # Integration tests
├── utils/
│   └── helpers.py               # Shared constants & JS analysis helpers
└── reports/
    ├── html_report.py           # Custom HTML report generator plugin
    └── .gitignore               # Exclude generated artifacts
=======
├── __init__.py              # Package marker
├── conftest.py              # Shared pytest fixtures
├── README.md                # This file
│
├── e2e/                     # End-to-end / Playwright UI tests
│   ├── test_js_console.py       # Browser JS console error detection
│   └── test_frontend.html       # Frontend JavaScript unit tests (browser)
│
├── api/                     # Backend API tests
│   ├── healthcheck/             # Health & liveness probes
│   │   ├── test_endpoints.py        # Live-server endpoint validation
│   │   └── test_health_responses.py # Comprehensive response tests (mocked)
│   ├── sanity/                  # Core API smoke tests
│   │   ├── test_api_endpoints.py    # Flask HTTP endpoint tests
│   │   ├── test_openai_api.py       # OpenAI-compatible API tests
│   │   └── test_voice_studio.py     # Voice Studio blueprint tests
│   └── regression/              # Regression / compatibility tests
│       └── test_openai_compatibility.py  # OpenAI format compatibility
│
├── integration/             # Integration tests (external services)
│   ├── test_integration.py          # TTS/STT/LLM integration
│   ├── test_openai_integration.py   # Real-world OpenAI scenarios
│   ├── test_search.py               # Chat search workflows
│   ├── test_audiobook_ws.py         # Audiobook WebSocket features
│   └── providers/                   # Provider integration tests
│       ├── test_cerebras_model_status.py      # Cerebras API tests
│       └── test_cerebras_real_connection.py    # Cerebras live connection
│
└── unit/                    # Unit tests (no external deps)
    ├── test_unit_backend.py         # Backend utility functions
    ├── test_huggingface_url.py      # HuggingFace URL parsing
    ├── test_audiobook_director.py   # Audiobook director subsystem
    ├── test_new_features.py         # New audiobook features
    ├── test_no_new_audio_per_chunk.py # Audio streaming implementation
    ├── test_js_variables.py         # JS global variable conflict detection
    └── providers/                   # Provider unit tests
        ├── test_providers.py                   # Individual providers
        ├── test_providers_comprehensive.py     # Comprehensive provider tests
        ├── test_cerebras_model_status_simple.py # Cerebras simple tests
        └── test_registry.py                    # Provider registry
>>>>>>> cb63dc998e1562d350c6448678bc91ab0705136f
```

## 🚀 Quick Start

### Prerequisites

```bash
<<<<<<< HEAD
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
cd src/tests

# All tests
python -m pytest -v --rootdir . -c pytest.ini

# Single file
python -m pytest e2e/test_smoke.py -v --rootdir . -c pytest.ini

# With custom report
python -m pytest -v --rootdir . -c pytest.ini -p reports.html_report
```

## 📊 Custom HTML Report
=======
# Run all tests
python run_tests.py

# Or use pytest directly
python -m pytest src/tests/ -v
```

### By Category

```bash
# Unit tests only
python run_tests.py --type unit
python -m pytest src/tests/unit/ -v

# API tests (healthcheck + sanity + regression)
python run_tests.py --type api
python -m pytest src/tests/api/ -v

# Healthcheck tests only
python run_tests.py --type healthcheck
python -m pytest src/tests/api/healthcheck/ -v

# Integration tests
python run_tests.py --type integration
python -m pytest src/tests/integration/ -v

# E2E tests (requires running server + browser)
python run_tests.py --type e2e
python -m pytest src/tests/e2e/ -v

# OpenAI API tests
python run_tests.py --type openai
```

### Test Categories

#### 1. Unit Tests (`unit/`)
Tests for individual functions without external dependencies.

**Coverage:**
- Text processing (emoji removal, thinking extraction)
- Dialogue parsing for audiobook
- Speaker gender detection, voice assignment
- Token estimation, settings management
- WAV generation, HuggingFace URL parsing
- Provider implementations and registry
- JavaScript variable conflict detection

#### 2. API Tests (`api/`)

##### Healthcheck (`api/healthcheck/`)
Health endpoint validation and response schema tests.

**Coverage:**
- `/health` liveness probe (status, schema, content-type)
- `/api/health` provider connectivity (connected, disconnected, exceptions)
- `/api/providers/status` all provider statuses
- `/api/services/status` TTS/STT microservice health
- `/api/llamacpp/server/status` llama.cpp server
- Response consistency and authentication requirements

##### Sanity (`api/sanity/`)
Core API endpoint smoke tests using test clients.

**Coverage:**
- Health, settings, sessions, models endpoints
- Chat, TTS, STT endpoints
- Voice cloning, audiobook, podcast endpoints
- OpenAI-compatible API endpoints
- Voice Studio blueprint

##### Regression (`api/regression/`)
Backward-compatibility and format regression tests.

**Coverage:**
- OpenAI response format compatibility
- Streaming response format
- Error response format

#### 3. Integration Tests (`integration/`)
Tests that verify actual external services work correctly.

**Environment Variables:**
- `TEST_LLM=1` - Enable LLM provider tests
- `TEST_TTS=1` - Enable TTS server tests
- `TEST_STT=1` - Enable STT server tests
- `TTS_URL` - TTS server URL (default: http://localhost:8020)
- `STT_URL` - STT server URL (default: http://localhost:8000)
- `LLM_URL` - LM Studio URL (default: http://localhost:1234)
- `CEREBRAS_API_KEY` - Cerebras API key for cloud tests
- `OPENROUTER_API_KEY` - OpenRouter API key for cloud tests

#### 4. E2E Tests (`e2e/`)
End-to-end browser tests.

**Coverage:**
- JavaScript console error detection
- Frontend unit tests (token estimation, thinking extraction, etc.)
>>>>>>> cb63dc998e1562d350c6448678bc91ab0705136f

A professional HTML report is auto-generated at `src/tests/reports/report.html`:

<<<<<<< HEAD
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

| Suite               | File                                       | Tests | Needs Server? |
| ------------------- | ------------------------------------------ | ----- | ------------- |
| Smoke Tests         | `e2e/test_smoke.py`                        | 24    | ✅ Yes        |
| JS Console Errors   | `e2e/test_js_console.py`                   | 3     | ✅ Yes        |
| Frontend Unit Tests | `e2e/test_frontend.py`                     | 30    | ✅ Yes        |
| JS Variable Analysis| `e2e/test_js_variables.py`                 | 4     | ❌ No         |
| API Endpoints       | `api/sanity/test_api_endpoints.py`         | 9     | ❌ No (Flask) |
| Search              | `api/regression/test_search_api.py`        | 14    | ❌ No (Flask) |
| Healthcheck         | `api/healthcheck/test_health_responses.py` | 12    | ❌ No (Flask) |

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
=======
```bash
python run_tests.py --coverage
```

## Writing New Tests

Place new tests in the appropriate category directory:

| Test type | Directory | When to use |
|-----------|-----------|-------------|
| Unit | `unit/` | Testing individual functions, no external deps |
| API healthcheck | `api/healthcheck/` | Health endpoint tests |
| API sanity | `api/sanity/` | Core endpoint smoke tests |
| API regression | `api/regression/` | Backward-compatibility tests |
| Integration | `integration/` | Tests requiring running services |
| E2E | `e2e/` | Browser-based tests |

### Example

```python
# src/tests/unit/test_my_feature.py
class TestMyFeature:
    """Tests for new feature."""

    def test_basic_functionality(self):
        result = my_function("input")
        assert result == "expected"

    def test_with_fixture(self, client):
        response = client.get('/api/endpoint')
        assert response.status_code == 200
```

## Test Best Practices

1. **Isolation**: Each test should be independent
2. **Cleanup**: Remove test data after tests complete
3. **Mocking**: Use mocks for external services in unit tests
4. **Descriptive names**: Test names should describe what they test
5. **One assertion**: Focus on one thing per test when possible
6. **Categorize correctly**: Place tests in the right directory
>>>>>>> cb63dc998e1562d350c6448678bc91ab0705136f
