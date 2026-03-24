# Test Suite for LM Studio Chatbot

This directory contains comprehensive tests for the chatbot application.

## Test Structure

```
tests/
├── __init__.py              # Package marker
├── conftest.py              # Pytest fixtures
├── test_unit_backend.py     # Unit tests for backend functions
├── test_api_endpoints.py    # API endpoint tests
├── test_integration.py      # Integration tests for external services
├── test_frontend.html       # Frontend JavaScript tests
└── README.md                # This file
```

## Running Tests

### Quick Start

```bash
# Run all tests
run_tests.bat

# Or use pytest directly
python -m pytest tests/ -v
```

### Test Categories

#### 1. Unit Tests (`test_unit_backend.py`)
Tests for individual functions without external dependencies.

```bash
run_tests.bat unit
# or
python -m pytest tests/test_unit_backend.py -v
```

**Coverage:**
- Text processing (emoji removal, thinking extraction)
- Dialogue parsing for audiobook
- Speaker gender detection
- Voice assignment logic
- Token estimation
- Settings management
- WAV generation

#### 2. API Endpoint Tests (`test_api_endpoints.py`)
Tests for Flask HTTP endpoints using test client.

```bash
run_tests.bat api
# or
python -m pytest tests/test_api_endpoints.py -v
```

**Coverage:**
- Health endpoints
- Settings CRUD
- Session management
- Model listing
- Chat endpoint
- TTS synthesis
- STT transcription
- Voice cloning
- Audiobook generation
- Service status
- SSE streaming

#### 3. Integration Tests (`test_integration.py`)
Tests that verify actual external services work correctly.

```bash
# Enable specific service tests with environment variables
set TEST_LLM=1
set TEST_TTS=1
set TEST_STT=1

run_tests.bat integration
```

**Environment Variables:**
- `TEST_LLM=1` - Enable LLM provider tests
- `TEST_TTS=1` - Enable TTS server tests
- `TEST_STT=1` - Enable STT server tests
- `TTS_URL` - TTS server URL (default: http://localhost:8020)
- `STT_URL` - STT server URL (default: http://localhost:8000)
- `LLM_URL` - LM Studio URL (default: http://localhost:1234)
- `CEREBRAS_API_KEY` - Cerebras API key for cloud tests
- `OPENROUTER_API_KEY` - OpenRouter API key for cloud tests

#### 4. Frontend Tests (`test_frontend.html`)
JavaScript unit tests run in the browser.

```bash
# Open in browser
start tests/test_frontend.html
```

**Coverage:**
- Token estimation
- Thinking extraction
- WAV buffer creation
- Speaker gender detection
- Dialogue parsing
- Emoji removal
- Base64 encoding
- SSE parsing
- Voice profiles
- Markdown rendering
- Audio playback

### Coverage Reports

Generate detailed coverage reports:

```bash
run_tests.bat coverage
```

This creates:
- Terminal output with coverage percentages
- `htmlcov/index.html` - Detailed HTML coverage report

## Writing New Tests

### Backend Tests

```python
class TestNewFeature:
    """Tests for new feature."""
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        result = my_function("input")
        assert result == "expected"
    
    def test_with_fixture(self, client):
        """Test using Flask test client."""
        response = client.get('/api/endpoint')
        assert response.status_code == 200
```

### Frontend Tests

```javascript
describe('New Feature', {
    'test basic functionality': () => {
        const result = myFunction('input');
        assertEqual(result, 'expected');
    },
    
    'test edge case': () => {
        const result = myFunction('');
        assertEqual(result, null);
    }
});
```

## Test Best Practices

1. **Isolation**: Each test should be independent
2. **Cleanup**: Remove test data after tests complete
3. **Mocking**: Use mocks for external services in unit tests
4. **Descriptive names**: Test names should describe what they test
5. **One assertion**: Focus on one thing per test when possible

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pip install -r requirements.txt
    python -m pytest tests/ -v --tb=short
```

## Troubleshooting

### Import Errors
Make sure the parent directory is in the Python path. The conftest.py handles this automatically.

### Service Not Running
Integration tests will skip if services are not available. Start services before running:

```bash
# Start TTS
python chatterbox_tts_server.py

# Start STT
cd parakeet-tdt-0.6b-v2 && python app.py

# Start LLM (LM Studio)
# Open LM Studio application
```

### Database Conflicts
Tests create temporary sessions that are cleaned up after each test. If you see conflicts, clear the sessions file:

```bash
rm resources/data/sessions.json