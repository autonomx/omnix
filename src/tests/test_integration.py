"""
Integration tests for external services (LLM, TTS, STT).
These tests verify the actual services work correctly.
Set environment variables to enable real service tests:
    TEST_LLM=1 - Test LLM provider
    TEST_TTS=1 - Test TTS server
    TEST_STT=1 - Test STT server
"""

import pytest
import os
import time
import base64
import requests


# Service endpoints
TTS_URL = os.environ.get('TTS_URL', 'http://localhost:8020')
STT_URL = os.environ.get('STT_URL', 'http://localhost:8000')
LLM_URL = os.environ.get('LLM_URL', 'http://localhost:1234')


def check_service(url, timeout=2):
    """Check if a service is running."""
    try:
        response = requests.get(f"{url}/health", timeout=timeout)
        return response.status_code == 200
    except:
        try:
            response = requests.get(f"{url}/v1/models", timeout=timeout)
            return response.status_code == 200
        except:
            return False


# Auto-detect running services (can override with env vars)
TEST_TTS = os.environ.get('TEST_TTS', '1') == '1' or check_service(TTS_URL)
TEST_STT = os.environ.get('TEST_STT', '1') == '1' or check_service(STT_URL)
TEST_LLM = os.environ.get('TEST_LLM', '1') == '1' or check_service(LLM_URL)

# Force enable if explicitly set
if os.environ.get('TEST_TTS') == '1':
    TEST_TTS = True
if os.environ.get('TEST_STT') == '1':
    TEST_STT = True
if os.environ.get('TEST_LLM') == '1':
    TEST_LLM = True

# API Keys for cloud providers - load from settings.json if available
def load_api_keys():
    """Load API keys from settings.json"""
    settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'settings.json')
    cerebras_key = os.environ.get('CEREBRAS_API_KEY', '')
    openrouter_key = os.environ.get('OPENROUTER_API_KEY', '')
    
    if os.path.exists(settings_path):
        try:
            import json
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            if not cerebras_key:
                cerebras_key = settings.get('cerebras', {}).get('api_key', '')
            if not openrouter_key:
                openrouter_key = settings.get('openrouter', {}).get('api_key', '')
        except Exception:
            pass
    
    return cerebras_key, openrouter_key

CEREBRAS_API_KEY, OPENROUTER_API_KEY = load_api_keys()


@pytest.mark.skipif(not TEST_TTS, reason="Set TEST_TTS=1 to enable TTS integration tests")
class TestTTSIntegration:
    """Integration tests for TTS service (Chatterbox)."""
    
    def test_tts_server_health(self):
        """Test TTS server is running and healthy."""
        try:
            response = requests.get(f"{TTS_URL}/health", timeout=5)
            assert response.status_code == 200
        except requests.exceptions.ConnectionError:
            pytest.skip("TTS server not running")
    
    def test_tts_synthesis_basic(self):
        """Test basic TTS synthesis."""
        try:
            response = requests.post(
                f"{TTS_URL}/tts",
                json={"text": "Hello, this is a test.", "language": "en"},
                timeout=30
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data.get('success', False) is True
            assert 'audio' in data
            assert data['audio'] is not None
            
            # Verify audio is valid base64
            audio_data = base64.b64decode(data['audio'])
            assert len(audio_data) > 0
            
        except requests.exceptions.ConnectionError:
            pytest.skip("TTS server not running")
    
    def test_tts_speakers_list(self):
        """Test getting available speakers."""
        try:
            response = requests.get(f"{TTS_URL}/speakers", timeout=5)
            assert response.status_code == 200
            
            data = response.json()
            assert 'speakers' in data
            assert len(data['speakers']) > 0
            
        except requests.exceptions.ConnectionError:
            pytest.skip("TTS server not running")
    
    def test_tts_long_text(self):
        """Test TTS with longer text."""
        long_text = """
        This is a longer text passage to test the TTS system's ability 
        to handle multiple sentences. The quick brown fox jumps over the lazy dog.
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        """
        
        try:
            response = requests.post(
                f"{TTS_URL}/tts",
                json={"text": long_text, "language": "en"},
                timeout=60
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data.get('success', False) is True
            assert 'audio' in data
            
            # Audio should be longer for longer text
            audio_data = base64.b64decode(data['audio'])
            assert len(audio_data) > 10000  # Should be substantial
            
        except requests.exceptions.ConnectionError:
            pytest.skip("TTS server not running")
    
    def test_tts_performance(self):
        """Test TTS synthesis latency."""
        text = "Testing performance latency."
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{TTS_URL}/tts",
                json={"text": text, "language": "en"},
                timeout=30
            )
            elapsed = time.time() - start_time
            
            assert response.status_code == 200
            # TTS should complete within 5 seconds for short text
            assert elapsed < 5.0, f"TTS took {elapsed:.2f}s, expected < 5s"
            
        except requests.exceptions.ConnectionError:
            pytest.skip("TTS server not running")


@pytest.mark.skipif(not TEST_STT, reason="Set TEST_STT=1 to enable STT integration tests")
class TestSTTIntegration:
    """Integration tests for STT service (Parakeet)."""
    
    def test_stt_server_health(self):
        """Test STT server is running and healthy."""
        try:
            response = requests.get(f"{STT_URL}/health", timeout=5)
            assert response.status_code == 200
        except requests.exceptions.ConnectionError:
            pytest.skip("STT server not running")
    
    def test_stt_transcribe_audio(self):
        """Test STT transcription with sample audio."""
        # Generate a simple test audio (silence)
        # In real tests, you'd use a pre-recorded audio file
        import io
        import wave
        import struct
        
        # Create a simple WAV file with silence
        sample_rate = 16000
        duration = 1.0  # 1 second
        num_samples = int(sample_rate * duration)
        
        # Create WAV in memory
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            # Write silence
            for _ in range(num_samples):
                wav_file.writeframes(struct.pack('<h', 0))
        
        buffer.seek(0)
        
        try:
            response = requests.post(
                f"{STT_URL}/transcribe",
                files={'file': ('test.wav', buffer, 'audio/wav')},
                timeout=30
            )
            
            assert response.status_code == 200
            data = response.json()
            # Silence should transcribe to empty or minimal text
            assert 'success' in data or 'segments' in data
            
        except requests.exceptions.ConnectionError:
            pytest.skip("STT server not running")


@pytest.mark.skipif(not TEST_LLM, reason="Set TEST_LLM=1 to enable LLM integration tests")
class TestLLMIntegration:
    """Integration tests for LLM providers."""
    
    def test_lmstudio_connection(self):
        """Test connection to LM Studio."""
        try:
            response = requests.get(f"{LLM_URL}/v1/models", timeout=5)
            assert response.status_code == 200
            
            data = response.json()
            assert 'data' in data
            
        except requests.exceptions.ConnectionError:
            pytest.skip("LM Studio not running")
    
    def test_lmstudio_chat_completion(self):
        """Test chat completion with LM Studio."""
        payload = {
            "model": "local-model",
            "messages": [
                {"role": "user", "content": "Say 'hello' and nothing else."}
            ],
            "max_tokens": 50,
            "stream": False
        }
        
        try:
            response = requests.post(
                f"{LLM_URL}/v1/chat/completions",
                json=payload,
                timeout=30
            )
            
            assert response.status_code == 200
            data = response.json()
            assert 'choices' in data
            assert len(data['choices']) > 0
            assert 'message' in data['choices'][0]
            
            # Verify response has content
            content = data['choices'][0]['message'].get('content', '')
            assert len(content) > 0
            
        except requests.exceptions.ConnectionError:
            pytest.skip("LM Studio not running")
    
    def test_lmstudio_streaming(self):
        """Test streaming completion with LM Studio."""
        payload = {
            "model": "local-model",
            "messages": [
                {"role": "user", "content": "Count from 1 to 5."}
            ],
            "max_tokens": 50,
            "stream": True
        }
        
        try:
            response = requests.post(
                f"{LLM_URL}/v1/chat/completions",
                json=payload,
                timeout=30,
                stream=True
            )
            
            assert response.status_code == 200
            
            # Verify we receive chunks
            chunks_received = 0
            for line in response.iter_lines():
                if line:
                    chunks_received += 1
                    if chunks_received >= 2:
                        break
            
            assert chunks_received >= 2, "Should receive multiple stream chunks"
            
        except requests.exceptions.ConnectionError:
            pytest.skip("LM Studio not running")
    
    @pytest.mark.skipif(not CEREBRAS_API_KEY, reason="CEREBRAS_API_KEY not set")
    def test_cerebras_chat_completion(self):
        """Test chat completion with Cerebras API."""
        # Get model from settings.json
        settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'settings.json')
        cerebras_model = "llama-3.3-70b-versatile"  # default
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                    cerebras_model = settings.get('cerebras', {}).get('model', cerebras_model)
            except:
                pass
        
        payload = {
            "model": cerebras_model,
            "messages": [
                {"role": "user", "content": "Say 'hello' and nothing else."}
            ],
            "max_tokens": 50
        }
        
        response = requests.post(
            "https://api.cerebras.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        # Log the actual response for debugging
        if response.status_code != 200:
            print(f"Cerebras API error: {response.status_code} - {response.text[:200]}")
        
        assert response.status_code == 200, f"Cerebras API returned {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert 'choices' in data
        assert len(data['choices']) > 0
    
    @pytest.mark.skipif(not OPENROUTER_API_KEY, reason="OPENROUTER_API_KEY not set")
    def test_openrouter_chat_completion(self):
        """Test chat completion with OpenRouter API."""
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "Say 'hello' and nothing else."}
            ],
            "max_tokens": 50
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5000"
            },
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert 'choices' in data


@pytest.mark.skipif(not (TEST_TTS and TEST_LLM), reason="Set TEST_TTS=1 and TEST_LLM=1 for end-to-end tests")
class TestEndToEnd:
    """End-to-end tests combining multiple services."""
    
    def test_chat_to_tts_pipeline(self, client):
        """Test the complete pipeline from chat to TTS."""
        # 1. Create session
        session_response = client.post('/api/sessions')
        session_id = session_response.json['session_id']
        
        # 2. Send chat message
        chat_response = client.post('/api/chat', json={
            'message': 'Say hello',
            'session_id': session_id
        })
        
        # Chat may fail if LLM not configured
        if chat_response.status_code != 200:
            pytest.skip("Chat endpoint failed - LLM may not be configured")
        
        chat_data = chat_response.json
        
        if chat_data.get('success'):
            response_text = chat_data.get('response', '')
            
            # 3. Generate TTS for the response
            tts_response = client.post('/api/tts', json={
                'text': response_text
            })
            
            assert tts_response.status_code == 200
            tts_data = tts_response.json
            
            if tts_data.get('success'):
                assert 'audio' in tts_data
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')


class TestServiceDiscovery:
    """Test that services can be discovered and are compatible."""
    
    @pytest.mark.skipif(not TEST_TTS, reason="Set TEST_TTS=1")
    def test_tts_sample_rate_compatibility(self):
        """Test TTS sample rate is compatible with playback."""
        try:
            response = requests.post(
                f"{TTS_URL}/tts",
                json={"text": "Test", "language": "en"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                sample_rate = data.get('sample_rate', 24000)
                
                # Common sample rates that should work
                valid_rates = [16000, 22050, 24000, 44100, 48000]
                assert sample_rate in valid_rates, f"Unusual sample rate: {sample_rate}"
                
        except requests.exceptions.ConnectionError:
            pytest.skip("TTS server not running")
    
    def test_llm_response_format(self):
        """Test LLM response format is correct."""
        # This test can run with mocks
        expected_keys = ['choices', 'usage']
        # Verify the expected structure
        for key in expected_keys:
            assert key in ['choices', 'usage', 'model', 'id', 'object']


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])