#!/usr/bin/env python3
"""
Tests for OpenAI Compatible API
Tests the FastAPI endpoints for OpenAI compatibility
"""

import pytest
import json
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Import the API app
from openai_api import app, AVAILABLE_MODELS, AVAILABLE_VOICES

client = TestClient(app)


class TestOpenAIModels:
    """Test the /v1/models endpoint"""
    
    def test_list_models(self):
        """Test listing available models"""
        response = client.get("/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        assert "object" in data
        assert data["object"] == "list"
        assert "data" in data
        assert isinstance(data["data"], list)
        
        # Check that all available models are listed
        model_ids = [model["id"] for model in data["data"]]
        for model in AVAILABLE_MODELS:
            assert model in model_ids
        
        # Check model structure
        for model in data["data"]:
            assert "id" in model
            assert "object" in model
            assert "created" in model
            assert "owned_by" in model
            assert model["object"] == "model"
            assert model["owned_by"] == "omnix"


class TestOpenAIVoices:
    """Test the /v1/audio/voices endpoints"""
    
    def test_list_voices(self):
        """Test listing available voices"""
        response = client.get("/v1/audio/voices")
        assert response.status_code == 200
        
        data = response.json()
        assert "voices" in data
        assert isinstance(data["voices"], list)
        
        # Check voice structure
        for voice in data["voices"]:
            assert "voice_id" in voice
            assert "name" in voice
            assert "category" in voice
            assert isinstance(voice["voice_id"], str)
            assert isinstance(voice["name"], str)
            assert isinstance(voice["category"], str)
    
    def test_get_voice_details(self):
        """Test getting specific voice details"""
        # Test with a known voice
        if AVAILABLE_VOICES:
            voice_id = AVAILABLE_VOICES[0].voice_id
            response = client.get(f"/v1/audio/voices/{voice_id}")
            assert response.status_code == 200
            
            data = response.json()
            assert data["voice_id"] == voice_id
            assert "name" in data
            assert "category" in data
    
    def test_get_nonexistent_voice(self):
        """Test getting a voice that doesn't exist"""
        response = client.get("/v1/audio/voices/nonexistent-voice")
        assert response.status_code == 404
        
        data = response.json()
        assert "detail" in data
        assert "Voice not found" in data["detail"]


class TestOpenAISpeech:
    """Test the /v1/audio/speech endpoint"""
    
    @patch('openai_api.tts_manager')
    @patch('openai_api.voice_manager')
    def test_create_speech_success(self, mock_voice_manager, mock_tts_manager):
        """Test successful speech generation"""
        # Mock TTS manager
        mock_tts_manager.generate_speech = AsyncMock(return_value=True)
        
        # Mock voice manager
        mock_voice_manager.get_available_voices.return_value = ["test_voice.wav"]
        mock_voice_manager.get_voice_file.return_value = "test_voice.wav"
        
        # Create test request
        request_data = {
            "model": "tts-1",
            "voice": "test_voice",
            "input": "Hello, this is a test message.",
            "speed": 1.0,
            "response_format": "mp3",
            "stream": False
        }
        
        response = client.post("/v1/audio/speech", json=request_data)
        
        # Should return streaming response (audio)
        assert response.status_code == 200
        # Note: We can't easily test the audio content in a unit test
    
    @patch('openai_api.voice_manager')
    def test_create_speech_no_voice_available(self, mock_voice_manager):
        """Test speech generation with no voices available"""
        mock_voice_manager.get_available_voices.return_value = []
        
        request_data = {
            "model": "tts-1",
            "voice": "test_voice",
            "input": "Hello, this is a test message.",
            "speed": 1.0,
            "response_format": "mp3",
            "stream": False
        }
        
        response = client.post("/v1/audio/speech", json=request_data)
        assert response.status_code == 400
        
        data = response.json()
        assert "No voice available" in data["detail"]
    
    def test_create_speech_invalid_request(self):
        """Test speech generation with invalid request data"""
        request_data = {
            "model": "tts-1",
            # Missing required fields
        }
        
        response = client.post("/v1/audio/speech", json=request_data)
        assert response.status_code == 422  # Validation error


class TestOpenAIChat:
    """Test the /v1/chat/completions endpoint"""
    
    def test_create_chat_completion_success(self):
        """Test successful chat completion"""
        request_data = {
            "model": "mistral-7b-instruct-v0.2",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "temperature": 0.7,
            "max_tokens": 100,
            "stream": False
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        
        # Check response structure
        assert "id" in data
        assert "object" in data
        assert data["object"] == "chat.completion"
        assert "created" in data
        assert "model" in data
        assert "choices" in data
        assert "usage" in data
        
        # Check choices structure
        assert isinstance(data["choices"], list)
        assert len(data["choices"]) == 1
        
        choice = data["choices"][0]
        assert "index" in choice
        assert "message" in choice
        assert "finish_reason" in choice
        
        # Check message structure
        message = choice["message"]
        assert "role" in message
        assert "content" in message
        assert message["role"] == "assistant"
    
    def test_create_chat_completion_streaming(self):
        """Test streaming chat completion"""
        request_data = {
            "model": "mistral-7b-instruct-v0.2",
            "messages": [
                {"role": "user", "content": "Tell me a short story."}
            ],
            "stream": True
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        
        # Check that it's a streaming response
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    def test_create_chat_completion_invalid_model(self):
        """Test chat completion with invalid model"""
        request_data = {
            "model": "invalid-model",
            "messages": [
                {"role": "user", "content": "Hello?"}
            ],
            "stream": False
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        # Should still work as we don't validate model names strictly
        assert response.status_code == 200
    
    def test_create_chat_completion_no_messages(self):
        """Test chat completion with no messages"""
        request_data = {
            "model": "mistral-7b-instruct-v0.2",
            "messages": [],
            "stream": False
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200  # Should still return a response


class TestOpenAIHealth:
    """Test the /health endpoint"""
    
    @patch('openai_api.tts_manager')
    @patch('openai_api.stt_manager')
    def test_health_check(self, mock_stt_manager, mock_tts_manager):
        """Test health check endpoint"""
        # Mock manager status
        mock_tts_manager.is_ready.return_value = True
        mock_stt_manager.is_ready.return_value = True
        
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "tts_available" in data
        assert "stt_available" in data
        assert "timestamp" in data
        assert data["tts_available"] is True
        assert data["stt_available"] is True


class TestOpenAIEndpoints:
    """Test other OpenAI endpoints"""
    
    def test_voice_preview(self):
        """Test voice preview endpoint"""
        if AVAILABLE_VOICES:
            voice_id = AVAILABLE_VOICES[0].voice_id
            response = client.get(f"/v1/audio/voices/{voice_id}/preview")
            assert response.status_code == 200
            
            data = response.json()
            assert "message" in data
            assert voice_id in data["message"]


class TestOpenAIErrorHandling:
    """Test error handling in OpenAI endpoints"""
    
    @patch('openai_api.tts_manager')
    def test_speech_generation_error(self, mock_tts_manager):
        """Test error handling in speech generation"""
        mock_tts_manager.generate_speech = AsyncMock(return_value=False)
        
        request_data = {
            "model": "tts-1",
            "voice": "test_voice",
            "input": "Test message",
            "stream": False
        }
        
        response = client.post("/v1/audio/speech", json=request_data)
        assert response.status_code == 500
        
        data = response.json()
        assert "Failed to generate speech" in data["detail"]
    
    @patch('openai_api.tts_manager')
    def test_speech_generation_exception(self, mock_tts_manager):
        """Test exception handling in speech generation"""
        mock_tts_manager.generate_speech = AsyncMock(side_effect=Exception("Test error"))
        
        request_data = {
            "model": "tts-1",
            "voice": "test_voice",
            "input": "Test message",
            "stream": False
        }
        
        response = client.post("/v1/audio/speech", json=request_data)
        assert response.status_code == 500


class TestOpenAIAPIIntegration:
    """Integration tests for the OpenAI API"""
    
    def test_api_documentation_available(self):
        """Test that FastAPI documentation is available"""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "Swagger UI" in response.text
    
    def test_api_openapi_schema(self):
        """Test that OpenAPI schema is available"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "/v1/models" in schema["paths"]
        assert "/v1/audio/voices" in schema["paths"]
        assert "/v1/audio/speech" in schema["paths"]
        assert "/v1/chat/completions" in schema["paths"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])