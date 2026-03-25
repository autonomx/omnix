"""
Pytest configuration and fixtures for LM Studio Chatbot tests.
"""

import pytest
import sys
import os

# Add parent directory and src to path for imports
# Works whether conftest is at src/tests/ or when discovered from subdirectories
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.dirname(_tests_dir)
_project_root = os.path.dirname(_src_dir)
sys.path.insert(0, _src_dir)
sys.path.insert(0, _project_root)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def app():
    """Create a test Flask app."""
    from app import app as flask_app
    
    # Configure for testing
    flask_app.config['TESTING'] = True
    
    yield flask_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return {
        "choices": [
            {
                "message": {
                    "content": "Hello! This is a test response from the AI."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }


@pytest.fixture
def mock_tts_response():
    """Mock TTS response for testing."""
    import base64
    # Simple WAV header + silence
    wav_data = b'RIFF' + (44).to_bytes(4, 'little') + b'WAVE'
    return {
        "success": True,
        "audio": base64.b64encode(wav_data).decode('utf-8'),
        "sample_rate": 24000
    }


@pytest.fixture
def mock_stt_response():
    """Mock STT response for testing."""
    return {
        "success": True,
        "segments": [
            {"text": "Hello world", "start": 0.0, "end": 1.0}
        ],
        "duration": 1.5
    }


@pytest.fixture
def sample_session_data():
    """Sample session data for testing."""
    return {
        "title": "Test Chat",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ],
        "system_prompt": "You are a helpful assistant."
    }


@pytest.fixture
def sample_audiobook_text():
    """Sample text for audiobook testing."""
    return """
    Narrator: The sun was setting over the hills.
    Sofia: What a beautiful evening!
    Morgan: Indeed, it reminds me of home.
    
    They walked together along the path, enjoying the peaceful moment.
    
    Sofia: I wish moments like this could last forever.
    """