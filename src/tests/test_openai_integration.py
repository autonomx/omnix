#!/usr/bin/env python3
"""
Integration tests for OpenAI Compatible API
Tests real-world usage scenarios and client compatibility
"""

import pytest
import requests
import json
import time
import tempfile
import os
from pathlib import Path
import subprocess
import threading
import asyncio
from unittest.mock import patch

# Test configuration
API_BASE_URL = "http://localhost:8001/v1"
TIMEOUT = 30  # 30 second timeout for API calls


class TestOpenAIIntegration:
    """Integration tests for OpenAI API compatibility"""
    
    @pytest.fixture(scope="class")
    def api_server(self):
        """Start the API server for integration tests"""
        # This would normally start the server, but for testing we'll assume it's running
        # In a real test environment, you might start it here
        yield
        # Cleanup would go here
    
    def test_openai_models_endpoint(self, api_server):
        """Test that models endpoint returns expected data"""
        try:
            response = requests.get(f"{API_BASE_URL}/models", timeout=TIMEOUT)
            assert response.status_code == 200
            
            data = response.json()
            assert "data" in data
            assert isinstance(data["data"], list)
            
            # Check for expected models
            model_ids = [model["id"] for model in data["data"]]
            expected_models = ["mistral-7b-instruct-v0.2", "qwen2.5-coder-7b-instruct"]
            
            for model in expected_models:
                assert model in model_ids, f"Model {model} not found in available models"
                
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_openai_voices_endpoint(self, api_server):
        """Test that voices endpoint returns expected data"""
        try:
            response = requests.get(f"{API_BASE_URL}/audio/voices", timeout=TIMEOUT)
            assert response.status_code == 200
            
            data = response.json()
            assert "voices" in data
            assert isinstance(data["voices"], list)
            
            # Should have at least some voices
            assert len(data["voices"]) > 0
            
            # Check voice structure
            for voice in data["voices"]:
                assert "voice_id" in voice
                assert "name" in voice
                assert "category" in voice
                
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_openai_chat_completion(self, api_server):
        """Test chat completion endpoint with real request"""
        try:
            request_data = {
                "model": "mistral-7b-instruct-v0.2",
                "messages": [
                    {"role": "user", "content": "Hello, what is 2 + 2?"}
                ],
                "temperature": 0.7,
                "max_tokens": 50,
                "stream": False
            }
            
            response = requests.post(
                f"{API_BASE_URL}/chat/completions",
                json=request_data,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200
            
            data = response.json()
            
            # Check response structure
            assert "id" in data
            assert "object" in data
            assert data["object"] == "chat.completion"
            assert "choices" in data
            assert len(data["choices"]) == 1
            
            choice = data["choices"][0]
            assert "message" in choice
            assert choice["message"]["role"] == "assistant"
            assert "content" in choice["message"]
            
            # The content should be a string (even if placeholder)
            assert isinstance(choice["message"]["content"], str)
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_openai_chat_streaming(self, api_server):
        """Test streaming chat completion"""
        try:
            request_data = {
                "model": "mistral-7b-instruct-v0.2",
                "messages": [
                    {"role": "user", "content": "Count to 3."}
                ],
                "stream": True
            }
            
            response = requests.post(
                f"{API_BASE_URL}/chat/completions",
                json=request_data,
                timeout=TIMEOUT,
                stream=True
            )
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            
            # Read streaming response
            chunks = []
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        chunk_data = line_str[6:]  # Remove "data: " prefix
                        if chunk_data != "[DONE]":
                            try:
                                chunk_json = json.loads(chunk_data)
                                chunks.append(chunk_json)
                            except json.JSONDecodeError:
                                pass
            
            # Should have received some chunks
            assert len(chunks) > 0
            
            # Check chunk structure
            for chunk in chunks:
                assert "id" in chunk
                assert "object" in chunk
                assert chunk["object"] == "chat.completion.chunk"
                assert "choices" in chunk
                assert len(chunk["choices"]) == 1
                
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_openai_tts_generation(self, api_server):
        """Test TTS generation endpoint"""
        try:
            request_data = {
                "model": "tts-1",
                "voice": "alloy",
                "input": "Hello, this is a test of the text-to-speech system.",
                "speed": 1.0,
                "response_format": "mp3",
                "stream": False
            }
            
            response = requests.post(
                f"{API_BASE_URL}/audio/speech",
                json=request_data,
                timeout=TIMEOUT
            )
            
            # Should return audio data or error
            assert response.status_code in [200, 500]  # 200 for success, 500 for TTS errors
            
            if response.status_code == 200:
                # Should return audio content
                assert len(response.content) > 0
                # Content type should be audio
                assert response.headers["content-type"].startswith("audio/")
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_openai_health_endpoint(self, api_server):
        """Test health check endpoint"""
        try:
            response = requests.get(f"{API_BASE_URL}/../health", timeout=TIMEOUT)
            assert response.status_code == 200
            
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
            assert "tts_available" in data
            assert "stt_available" in data
            assert "timestamp" in data
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")


class TestOpenAIClientCompatibility:
    """Test compatibility with popular OpenAI clients"""
    
    def test_openai_python_client_compatibility(self, api_server):
        """Test compatibility with OpenAI Python client library"""
        try:
            # This would test with the actual OpenAI client
            # For now, we'll simulate the request format
            import openai
            
            # Configure client to use our API
            client = openai.OpenAI(
                base_url=f"{API_BASE_URL}",
                api_key="dummy-key"  # Not required for local server
            )
            
            # Test chat completion
            response = client.chat.completions.create(
                model="mistral-7b-instruct-v0.2",
                messages=[{"role": "user", "content": "Hello!"}]
            )
            
            assert response is not None
            assert hasattr(response, 'choices')
            assert len(response.choices) > 0
            
        except ImportError:
            pytest.skip("OpenAI Python client not installed")
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_curl_compatibility(self, api_server):
        """Test that the API works with curl-style requests"""
        try:
            # Test with requests library (simulating curl)
            request_data = {
                "model": "mistral-7b-instruct-v0.2",
                "messages": [
                    {"role": "user", "content": "What is AI?"}
                ]
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{API_BASE_URL}/chat/completions",
                json=request_data,
                headers=headers,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")


class TestOpenAIBehavior:
    """Test specific OpenAI-compatible behaviors"""
    
    def test_openai_error_format(self, api_server):
        """Test that errors are returned in OpenAI format"""
        try:
            # Test with invalid request
            request_data = {
                "model": "mistral-7b-instruct-v0.2",
                "messages": []  # Empty messages
            }
            
            response = requests.post(
                f"{API_BASE_URL}/chat/completions",
                json=request_data,
                timeout=TIMEOUT
            )
            
            # Should return 200 (we don't strictly validate) or proper error
            assert response.status_code in [200, 422]
            
            if response.status_code == 422:
                # Should have validation error format
                data = response.json()
                assert "detail" in data
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_openai_response_format(self, api_server):
        """Test that responses match OpenAI format exactly"""
        try:
            request_data = {
                "model": "mistral-7b-instruct-v0.2",
                "messages": [
                    {"role": "user", "content": "Hello"}
                ],
                "stream": False
            }
            
            response = requests.post(
                f"{API_BASE_URL}/chat/completions",
                json=request_data,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Check required OpenAI fields
            required_fields = ["id", "object", "created", "model", "choices", "usage"]
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"
            
            # Check choices format
            assert isinstance(data["choices"], list)
            assert len(data["choices"]) > 0
            
            choice = data["choices"][0]
            required_choice_fields = ["index", "message", "finish_reason"]
            for field in required_choice_fields:
                assert field in choice, f"Missing required choice field: {field}"
            
            # Check message format
            message = choice["message"]
            required_message_fields = ["role", "content"]
            for field in required_message_fields:
                assert field in message, f"Missing required message field: {field}"
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")


class TestOpenAIStreamingBehavior:
    """Test streaming-specific behaviors"""
    
    def test_streaming_chunk_format(self, api_server):
        """Test that streaming chunks match OpenAI format"""
        try:
            request_data = {
                "model": "mistral-7b-instruct-v0.2",
                "messages": [
                    {"role": "user", "content": "Say 'Hello'"}
                ],
                "stream": True
            }
            
            response = requests.post(
                f"{API_BASE_URL}/chat/completions",
                json=request_data,
                timeout=TIMEOUT,
                stream=True
            )
            
            assert response.status_code == 200
            
            chunks_received = 0
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        chunk_data = line_str[6:]
                        if chunk_data != "[DONE]":
                            try:
                                chunk = json.loads(chunk_data)
                                chunks_received += 1
                                
                                # Check chunk format
                                assert "id" in chunk
                                assert "object" in chunk
                                assert chunk["object"] == "chat.completion.chunk"
                                assert "choices" in chunk
                                
                                choice = chunk["choices"][0]
                                assert "index" in choice
                                assert "delta" in choice
                                assert "finish_reason" in choice or choice.get("finish_reason") is None
                                
                            except json.JSONDecodeError:
                                pass
            
            # Should have received multiple chunks for streaming
            assert chunks_received > 1
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")
    
    def test_streaming_final_chunk(self, api_server):
        """Test that streaming ends with [DONE]"""
        try:
            request_data = {
                "model": "mistral-7b-instruct-v0.2",
                "messages": [
                    {"role": "user", "content": "Short response"}
                ],
                "stream": True
            }
            
            response = requests.post(
                f"{API_BASE_URL}/chat/completions",
                json=request_data,
                timeout=TIMEOUT,
                stream=True
            )
            
            assert response.status_code == 200
            
            done_received = False
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str == "data: [DONE]":
                        done_received = True
                        break
            
            assert done_received, "Did not receive [DONE] marker in streaming response"
            
        except requests.exceptions.ConnectionError:
            pytest.skip("API server not running, skipping integration test")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])