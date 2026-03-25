# Test Suite for Omnix

This directory contains comprehensive tests for the Omnix application.

## Test Structure

```
src/tests/
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
```

## Running Tests

### Quick Start

```bash
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

### Coverage Reports

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