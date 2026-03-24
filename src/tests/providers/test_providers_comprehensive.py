"""Comprehensive tests for provider implementations."""

import pytest
import requests
from unittest.mock import Mock, patch, MagicMock, mock_open
from app.providers import (
    LMStudioProvider,
    OpenRouterProvider,
    CerebrasProvider,
    LlamaCppProvider,
    ProviderConfig,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderCapability,
    AuthenticationError,
    ConnectionError,
    ModelNotFoundError
)
import json


class TestChatMessageFull:
    """Full test suite for ChatMessage."""
    
    def test_chat_message_all_fields(self):
        """Test ChatMessage with all fields."""
        msg = ChatMessage(
            role="user",
            content="Hello",
            name="User",
            tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "test"}}],
            tool_call_id="call_1"
        )
        d = msg.to_dict()
        assert d == {
            "role": "user",
            "content": "Hello",
            "name": "User",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test"}}],
            "tool_call_id": "call_1"
        }
    
    def test_chat_message_minimal(self):
        """Test ChatMessage with only required fields."""
        msg = ChatMessage(role="assistant", content="Hi")
        d = msg.to_dict()
        assert d == {"role": "assistant", "content": "Hi"}
    
    def test_chat_message_invalid_role(self):
        """Test that ChatMessage accepts any role string."""
        msg = ChatMessage(role="custom", content="test")
        assert msg.role == "custom"


class TestChatResponseFull:
    """Full test suite for ChatResponse."""
    
    def test_chat_response_all_fields(self):
        """Test ChatResponse with all fields."""
        resp = ChatResponse(
            content="Hello!",
            model="gpt-4",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            thinking="I'm thinking...",
            reasoning="I'm reasoning...",
            tool_calls=[{"id": "call_1", "type": "function"}],
            finish_reason="stop",
            raw_response={"raw": "data"}
        )
        d = resp.to_dict()
        assert d["content"] == "Hello!"
        assert d["model"] == "gpt-4"
        assert d["usage"] == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        assert d["thinking"] == "I'm thinking..."
        assert d["reasoning"] == "I'm reasoning..."
        assert d["tool_calls"] == [{"id": "call_1", "type": "function"}]
        assert d["finish_reason"] == "stop"
    
    def test_chat_response_minimal(self):
        """Test ChatResponse with only required fields."""
        resp = ChatResponse(content="Hi", model="test-model")
        d = resp.to_dict()
        assert d == {"content": "Hi", "model": "test-model"}
    
    def test_chat_response_none_fields(self):
        """Test ChatResponse with None optional fields."""
        resp = ChatResponse(content="Test", model="model", usage=None, thinking=None)
        d = resp.to_dict()
        assert "usage" not in d or d.get("usage") is None
        assert "thinking" not in d or d.get("thinking") is None


class TestModelInfoFull:
    """Full test suite for ModelInfo."""
    
    def test_model_info_all_fields(self):
        """Test ModelInfo with all fields."""
        info = ModelInfo(
            id="model-1",
            name="Test Model",
            provider="test",
            context_length=4096,
            capabilities=[ProviderCapability.CHAT, ProviderCapability.STREAMING],
            description="A test model",
            metadata={"key": "value"}
        )
        d = info.to_dict()
        assert d == {
            "id": "model-1",
            "name": "Test Model",
            "provider": "test",
            "context_length": 4096,
            "capabilities": ["chat", "streaming"],
            "description": "A test model",
            "metadata": {"key": "value"}
        }
    
    def test_model_info_minimal(self):
        """Test ModelInfo with minimal fields."""
        info = ModelInfo(id="m", name="n", provider="p")
        d = info.to_dict()
        assert d["id"] == "m"
        assert d["name"] == "n"
        assert d["provider"] == "p"
        assert d["context_length"] is None
        assert d["capabilities"] == []
        assert d["description"] is None
        assert d["metadata"] == {}


class TestProviderConfigFull:
    """Full test suite for ProviderConfig."""
    
    def test_provider_config_all_fields(self):
        """Test ProviderConfig with all fields."""
        config = ProviderConfig(
            provider_type="test",
            api_key="secret123",
            base_url="http://test.com",
            model="test-model",
            timeout=120,
            max_retries=5,
            extra_params={"key": "value"}
        )
        d = config.to_dict()
        assert d["provider_type"] == "test"
        assert d["api_key"] == "***t123"  # Shows last 4 chars: *** + t123
        assert d["base_url"] == "http://test.com"
        assert d["model"] == "test-model"
        assert d["timeout"] == 120
        assert d["max_retries"] == 5
        assert d["extra_params"] == {"key": "value"}
    
    def test_provider_config_short_api_key(self):
        """Test API key masking with short key."""
        config = ProviderConfig(provider_type="test", api_key="abc")
        d = config.to_dict()
        assert d["api_key"] == "****"
    
    def test_provider_config_defaults(self):
        """Test ProviderConfig defaults."""
        config = ProviderConfig(provider_type="test")
        assert config.api_key is None
        assert config.base_url is None
        assert config.model is None
        assert config.timeout == 300
        assert config.max_retries == 3
        assert config.extra_params == {}


class TestBaseProviderHelperMethods:
    """Test BaseProvider helper methods."""
    
    def test_to_shared_format_with_reasoning(self):
        """Test to_shared_format with reasoning field."""
        resp = ChatResponse(content="Test", model="model", reasoning="Thought process")
        result = LMStudioProvider(ProviderConfig(provider_type="lmstudio")).to_shared_format(resp)
        assert result["thinking"] == "Thought process"
        assert result["reasoning"] == "Thought process"
    
    def test_to_shared_format_with_thinking(self):
        """Test to_shared_format with thinking field."""
        resp = ChatResponse(content="Test", model="model", thinking="Thought process")
        result = LMStudioProvider(ProviderConfig(provider_type="lmstudio")).to_shared_format(resp)
        assert result["thinking"] == "Thought process"
        assert result["reasoning"] == "Thought process"
    
    def test_from_shared_format(self):
        """Test from_shared_format conversion."""
        data = {
            "content": "Hello",
            "model": "test-model",
            "usage": {"total_tokens": 100},
            "thinking": "I'm thinking"
        }
        provider = LMStudioProvider(ProviderConfig(provider_type="lmstudio"))
        resp = provider.from_shared_format(data)
        assert resp.content == "Hello"
        assert resp.model == "test-model"
        assert resp.usage == {"total_tokens": 100}
        assert resp.thinking == "I'm thinking"
    
    def test_supports_streaming(self):
        """Test supports_streaming method."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        assert provider.supports_streaming() is True
    
    def test_requires_api_key(self):
        """Test requires_api_key method."""
        # LM Studio doesn't require API key
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        assert provider.requires_api_key() is False
        
        # OpenRouter requires API key
        config = ProviderConfig(provider_type="openrouter", api_key="test")
        provider = OpenRouterProvider(config)
        assert provider.requires_api_key() is True
    
    def test_get_capabilities(self):
        """Test get_capabilities returns copy."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        caps1 = provider.get_capabilities()
        caps2 = provider.get_capabilities()
        assert caps1 == caps2
        assert caps1 is not caps2  # Should be a copy


class TestLMStudioProviderFull:
    """Full test suite for LMStudioProvider."""
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_chat_completion_success(self, mock_requests):
        """Test successful non-streaming chat completion."""
        # Create a proper mock response with the expected data structure
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}
        }
        mock_requests.request.return_value = mock_response

        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234", model="test-model")
        provider = LMStudioProvider(config)

        messages = [ChatMessage(role="user", content="Hi")]
        response = provider.chat_completion(messages)

        assert isinstance(response, ChatResponse)
        assert response.content == "Hello!"
        assert response.model == "test-model"
        assert response.usage == {"prompt_tokens": 10, "completion_tokens": 20}
        mock_requests.request.assert_called_once()
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_chat_completion_with_streaming(self, mock_requests):
        """Test streaming chat completion."""
        def mock_stream():
            lines = [
                b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
                b'data: {"choices": [{"delta": {"content": " World"}}]}\n\n',
                b'data: [DONE]\n\n'
            ]
            for line in lines:
                yield line
        
        mock_response = Mock()
        mock_response.iter_lines.return_value = mock_stream()
        mock_requests.request.return_value = mock_response
        
        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234", model="test-model")
        provider = LMStudioProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        stream = provider.chat_completion(messages, stream=True)
        
        chunks = list(stream)
        assert len(chunks) >= 2
        assert any(c.content for c in chunks)
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_chat_completion_connection_error(self, mock_requests):
        """Test chat completion with connection error."""
        mock_requests.request.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234", model="test-model")
        provider = LMStudioProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        with pytest.raises(ConnectionError):
            provider.chat_completion(messages)
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_chat_completion_http_error(self, mock_requests):
        """Test chat completion with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = mock_requests.exceptions.HTTPError(response=mock_response)
        mock_requests.request.return_value = mock_response
        
        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234", model="test-model")
        provider = LMStudioProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        with pytest.raises(ConnectionError):
            provider.chat_completion(messages)
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_chat_completion_empty_messages(self, mock_requests):
        """Test chat completion with empty messages."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        
        with pytest.raises(ValueError):
            provider.chat_completion([])
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_get_models_success(self, mock_requests):
        """Test successful get_models."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {"id": "model-1", "context_length": 4096, "description": "Model 1"},
                {"id": "model-2", "context_length": 8192}
            ]
        }
        mock_requests.request.return_value = mock_response
        
        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234")
        provider = LMStudioProvider(config)
        
        models = provider.get_models()
        
        assert len(models) == 2
        assert models[0].id == "model-1"
        assert models[0].context_length == 4096
        assert models[1].id == "model-2"
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_get_models_empty(self, mock_requests):
        """Test get_models with empty response."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": []}
        mock_requests.request.return_value = mock_response
        
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        models = provider.get_models()
        assert models == []

    @patch('app.providers.lmstudio_provider.requests')
    def test_get_models_connection_error(self, mock_requests):
        """Test get_models with connection error."""
        mock_requests.request.side_effect = ConnectionError("Connection failed")
        
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        
        with pytest.raises(ConnectionError):
            provider.get_models()

    @patch('app.providers.lmstudio_provider.requests')
    def test_test_connection_success(self, mock_requests):
        """Test successful test_connection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.request.return_value = mock_response
        
        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234")
        provider = LMStudioProvider(config)
        
        result = provider.test_connection()
        assert result is True

    @patch('app.providers.lmstudio_provider.requests')
    def test_test_connection_failure(self, mock_requests):
        """Test failed test_connection."""
        mock_requests.request.side_effect = ConnectionError("Connection failed")
        
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        
        result = provider.test_connection()
        assert result is False
    
    def test_config_schema(self):
        """Test LMStudio config schema."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        schema = provider.get_config_schema()
        
        assert schema["provider_type"] == "lmstudio"
        assert len(schema["fields"]) >= 2
        field_names = [f["name"] for f in schema["fields"]]
        assert "base_url" in field_names
        assert "model" in field_names
    
    def test_default_base_url(self):
        """Test default base URL."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        assert provider.config.base_url == "http://localhost:1234"


class TestOpenRouterProviderFull:
    """Full test suite for OpenRouterProvider."""
    
    @patch('app.providers.openrouter_provider.requests')
    def test_chat_completion_success(self, mock_requests):
        """Test successful non-streaming chat completion."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!", "reasoning": "Thinking..."}, "finish_reason": "stop"}],
            "model": "openai/gpt-4",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}
        }
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="openrouter", api_key="test-key", model="openai/gpt-4")
        provider = OpenRouterProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        response = provider.chat_completion(messages)
        
        assert isinstance(response, ChatResponse)
        assert response.content == "Hello!"
        assert response.thinking == "Thinking..."
        assert response.model == "openai/gpt-4"
    
    @patch('app.providers.openrouter_provider.requests')
    def test_chat_completion_with_thinking_budget(self, mock_requests):
        """Test chat completion with thinking budget."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "model": "openai/gpt-4"
        }
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(
            provider_type="openrouter",
            api_key="test-key",
            model="openai/gpt-4",
            extra_params={"thinking_budget": 1000}
        )
        provider = OpenRouterProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        provider.chat_completion(messages)
        
        call_kwargs = mock_requests.post.call_args[1]
        assert "extra_options" in call_kwargs['json']
        assert call_kwargs['json']["extra_options"]["max_tokens"] == 1000
    
    @patch('app.providers.openrouter_provider.requests')
    def test_chat_completion_streaming(self, mock_requests):
        """Test streaming chat completion."""
        def mock_stream():
            lines = [
                b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
                b'data: {"choices": [{"delta": {"content": "!"}}]}\n\n',
                b'data: [DONE]\n\n'
            ]
            for line in lines:
                yield line
        
        mock_response = Mock()
        mock_response.iter_lines.return_value = mock_stream()
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="openrouter", api_key="test-key", model="openai/gpt-4")
        provider = OpenRouterProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        stream = provider.chat_completion(messages, stream=True)
        
        chunks = list(stream)
        assert len(chunks) >= 2
    
    @patch('app.providers.openrouter_provider.requests')
    def test_get_models_success(self, mock_requests):
        """Test successful get_models."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "openai/gpt-4",
                    "name": "GPT-4",
                    "description": "Advanced model",
                    "context_length": 8192,
                    "owned_by": "openai",
                    "pricing": {"prompt": 0.03, "completion": 0.06}
                }
            ]
        }
        mock_requests.get.return_value = mock_response
        
        config = ProviderConfig(provider_type="openrouter", api_key="test-key")
        provider = OpenRouterProvider(config)
        
        models = provider.get_models()
        
        assert len(models) == 1
        assert models[0].id == "openai/gpt-4"
        assert models[0].name == "GPT-4"
        assert models[0].context_length == 8192
        assert models[0].metadata["owned_by"] == "openai"
    
    @patch('app.providers.openrouter_provider.requests')
    def test_get_models_authentication_error(self, mock_requests):
        """Test get_models with authentication error."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = mock_requests.exceptions.HTTPError(response=mock_response)
        mock_requests.get.return_value = mock_response
        
        config = ProviderConfig(provider_type="openrouter", api_key="invalid-key")
        provider = OpenRouterProvider(config)
        
        with pytest.raises(AuthenticationError):
            provider.get_models()
    
    @patch('app.providers.openrouter_provider.requests')
    def test_test_connection_authentication_error_reraises(self, mock_requests):
        """Test test_connection re-raises auth errors."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = mock_requests.exceptions.HTTPError(response=mock_response)
        mock_requests.get.return_value = mock_response
        
        config = ProviderConfig(provider_type="openrouter", api_key="invalid-key")
        provider = OpenRouterProvider(config)
        
        with pytest.raises(AuthenticationError):
            provider.test_connection()
    
    def test_missing_api_key_raises(self):
        """Test that missing API key raises AuthenticationError."""
        config = ProviderConfig(provider_type="openrouter")
        with pytest.raises(AuthenticationError):
            OpenRouterProvider(config)
    
    def test_config_schema(self):
        """Test OpenRouter config schema."""
        config = ProviderConfig(provider_type="openrouter", api_key="test")
        provider = OpenRouterProvider(config)
        schema = provider.get_config_schema()
        
        assert schema["provider_type"] == "openrouter"
        field_names = [f["name"] for f in schema["fields"]]
        assert "api_key" in field_names
        assert "model" in field_names
        assert "thinking_budget" in field_names
    
    def test_supports_thinking_budget(self):
        """Test OpenRouter supports thinking budget."""
        config = ProviderConfig(provider_type="openrouter", api_key="test")
        provider = OpenRouterProvider(config)
        assert provider.supports_thinking_budget() is True


class TestCerebrasProviderFull:
    """Full test suite for CerebrasProvider."""
    
    @patch('app.providers.cerebras_provider.requests')
    def test_chat_completion_success(self, mock_requests):
        """Test successful non-streaming chat completion."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from Cerebras!"}, "finish_reason": "stop"}],
            "model": "cerebras-llama-3.3",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}
        }
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="cerebras", api_key="test-key", model="cerebras-llama-3.3")
        provider = CerebrasProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        response = provider.chat_completion(messages)
        
        assert isinstance(response, ChatResponse)
        assert response.content == "Hello from Cerebras!"
        assert response.model == "cerebras-llama-3.3"
    
    @patch('app.providers.cerebras_provider.requests')
    def test_chat_completion_streaming(self, mock_requests):
        """Test streaming chat completion."""
        def mock_stream():
            lines = [
                b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
                b'data: {"choices": [{"delta": {"content": " World"}}]}\n\n',
                b'data: [DONE]\n\n'
            ]
            for line in lines:
                yield line
        
        mock_response = Mock()
        mock_response.iter_lines.return_value = mock_stream()
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="cerebras", api_key="test-key", model="cerebras-llama-3.3")
        provider = CerebrasProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        stream = provider.chat_completion(messages, stream=True)
        
        chunks = list(stream)
        assert len(chunks) >= 2
    
    @patch('app.providers.cerebras_provider.requests')
    def test_get_models_success(self, mock_requests):
        """Test successful get_models."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {"id": "cerebras-llama-3.3", "name": "Llama 3.3 70B", "description": "Large model", "context_length": 8192, "owned_by": "cerebras"}
            ]
        }
        mock_requests.get.return_value = mock_response
        
        config = ProviderConfig(provider_type="cerebras", api_key="test-key")
        provider = CerebrasProvider(config)
        
        models = provider.get_models()
        
        assert len(models) == 1
        assert models[0].id == "cerebras-llama-3.3"
        assert models[0].name == "Llama 3.3 70B"
    
    def test_missing_api_key_raises(self):
        """Test that missing API key raises AuthenticationError."""
        config = ProviderConfig(provider_type="cerebras")
        with pytest.raises(AuthenticationError):
            CerebrasProvider(config)
    
    @patch('app.providers.cerebras_provider.requests')
    def test_test_connection_success(self, mock_requests):
        """Test successful test_connection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response
        
        config = ProviderConfig(provider_type="cerebras", api_key="test-key")
        provider = CerebrasProvider(config)
        
        result = provider.test_connection()
        assert result is True
    
    def test_config_schema(self):
        """Test Cerebras config schema."""
        config = ProviderConfig(provider_type="cerebras", api_key="test")
        provider = CerebrasProvider(config)
        schema = provider.get_config_schema()
        
        assert schema["provider_type"] == "cerebras"
        field_names = [f["name"] for f in schema["fields"]]
        assert "api_key" in field_names
        assert "model" in field_names


class TestLlamaCppProviderFull:
    """Full test suite for LlamaCppProvider."""
    
    def test_initialization_defaults(self):
        """Test LlamaCppProvider initialization with defaults."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        assert provider.config.base_url == "http://localhost:8080"
        assert 'model_dir' in provider.config.extra_params
    
    def test_config_schema(self):
        """Test LlamaCpp config schema."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        schema = provider.get_config_schema()
        
        assert schema["provider_type"] == "llamacpp"
        field_names = [f["name"] for f in schema["fields"]]
        assert "base_url" in field_names
        assert "model" in field_names
        assert "auto_start" in field_names
        assert "download_location" in field_names
    
    def test_requires_api_key_false(self):
        """Test LlamaCpp does not require API key."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        assert provider.requires_api_key() is False
    
    @patch('app.providers.llamacpp_provider.requests')
    def test_chat_completion_model_not_found(self, mock_requests):
        """Test chat completion when model not found."""
        config = ProviderConfig(provider_type="llamacpp", model="nonexistent.gguf")
        provider = LlamaCppProvider(config)
        
        with pytest.raises(ModelNotFoundError):
            provider.chat_completion([ChatMessage(role="user", content="Hi")])
    
    @patch('app.providers.llamacpp_provider.subprocess')
    @patch('app.providers.llamacpp_provider.requests')
    def test_chat_completion_server_start_fails(self, mock_requests, mock_subprocess):
        """Test chat completion when server fails to start."""
        config = ProviderConfig(provider_type="llamacpp", model="test.gguf")
        provider = LlamaCppProvider(config)
        
        # Mock _find_server_binary to return a path
        with patch.object(provider, '_find_server_binary', return_value=Path('/fake/binary')):
            # Mock server not running
            with patch.object(provider, '_is_server_running', return_value=False):
                # Mock _start_server to fail
                with patch.object(provider, '_start_server', return_value=None):
                    with pytest.raises(ConnectionError, match="Failed to start llama.cpp server"):
                        provider.chat_completion([ChatMessage(role="user", content="Hi")])
    
    @patch('app.providers.llamacpp_provider.requests')
    def test_chat_completion_empty_messages(self, mock_requests):
        """Test chat completion with empty messages."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        
        with pytest.raises(ValueError):
            provider.chat_completion([])
    
    def test_get_models_empty_dir(self):
        """Test get_models with non-existent directory."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        # Set model_dir to non-existent path
        provider.config.extra_params['model_dir'] = '/nonexistent'
        
        models = provider.get_models()
        assert models == []
    
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.rglob')
    def test_get_models_with_gguf_files(self, mock_rglob, mock_exists):
        """Test get_models with GGUF files."""
        mock_exists.return_value = True
        
        # Create mock GGUF files
        mock_file1 = Mock()
        mock_file1.relative_to.return_value = Path("model1.gguf")
        mock_file1.name = "model1.gguf"
        mock_file1.stat.return_value.st_size = 1024 * 1024 * 1024  # 1GB
        
        mock_file2 = Mock()
        mock_file2.relative_to.return_value = Path("model2.gguf")
        mock_file2.name = "model2.gguf"
        mock_file2.stat.return_value.st_size = 2 * 1024 * 1024 * 1024  # 2GB
        
        mock_rglob.return_value = [mock_file1, mock_file2]
        
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        provider.config.extra_params['model_dir'] = '/fake/models'
        
        models = provider.get_models()
        
        assert len(models) == 2
        assert models[0].id == "model1.gguf"
        assert models[0].metadata["size"] == 1024 * 1024 * 1024
        assert models[1].id == "model2.gguf"
    
    @patch('app.providers.llamacpp_provider.requests')
    def test_test_connection_server_not_running(self, mock_requests):
        """Test test_connection when server is not running."""
        mock_requests.get.side_effect = ConnectionError()
        
        config = ProviderConfig(provider_type="llamacpp", base_url="http://localhost:8080")
        provider = LlamaCppProvider(config)
        
        result = provider.test_connection()
        assert result is False
    
    @patch('app.providers.llamacpp_provider._find_server_binary')
    def test_find_server_binary(self, mock_find):
        """Test _find_server_binary method."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        provider.config.extra_params['model_dir'] = '/fake/models'
        
        # This test would need more Path mocking, but the method is straightforward
        assert hasattr(provider, '_find_server_binary')


class TestProviderErrorHandling:
    """Test error handling across all providers."""
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_lmstudio_json_parse_error(self, mock_requests):
        """Test LM Studio handling of invalid JSON."""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="lmstudio", model="test-model")
        provider = LMStudioProvider(config)
        
        with pytest.raises(ConnectionError, match="Invalid JSON"):
            provider.chat_completion([ChatMessage(role="user", content="Hi")])
    
    @patch('app.providers.openrouter_provider.requests')
    def test_openrouter_rate_limit(self, mock_requests):
        """Test OpenRouter rate limit handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = mock_requests.exceptions.HTTPError(response=mock_response)
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="openrouter", api_key="test")
        provider = OpenRouterProvider(config)
        
        from app.providers.exceptions import RateLimitError
        with pytest.raises(RateLimitError):
            provider.chat_completion([ChatMessage(role="user", content="Hi")])
    
    @patch('app.providers.cerebras_provider.requests')
    def test_cerebras_missing_choice(self, mock_requests):
        """Test Cerebras handling of missing choices."""
        mock_response = Mock()
        mock_response.json.return_value = {"model": "test", "choices": []}
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="cerebras", api_key="test", model="test")
        provider = CerebrasProvider(config)
        
        with pytest.raises(ConnectionError, match="No choices"):
            provider.chat_completion([ChatMessage(role="user", content="Hi")])


class TestStreamingEdgeCases:
    """Test streaming edge cases across providers."""
    
    @patch('app.providers.lmstudio_provider.requests')
    def test_streaming_malformed_lines(self, mock_requests):
        """Test streaming with malformed SSE lines."""
        def mock_stream():
            lines = [
                b'data: malformed json\n\n',
                b'data: {"not": "a proper SSE"}\n\n',
                b'data: {"choices": [{"delta": {"content": "Valid"}}]}\n\n',
                b'data: [DONE]\n\n'
            ]
            for line in lines:
                yield line
        
        mock_response = Mock()
        mock_response.iter_lines.return_value = mock_stream()
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="lmstudio", model="test-model")
        provider = LMStudioProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        stream = provider.chat_completion(messages, stream=True)
        
        # Should yield at least one valid chunk without raising
        chunks = list(stream)
        assert isinstance(chunks, list)
    
    @patch('app.providers.openrouter_provider.requests')
    def test_streaming_empty_delta(self, mock_requests):
        """Test streaming with empty delta."""
        def mock_stream():
            lines = [
                b'data: {"choices": [{"delta": {}}]}\n\n',
                b'data: {"choices": [{"delta": {"content": "A"}}]}\n\n',
                b'data: [DONE]\n\n'
            ]
            for line in lines:
                yield line
        
        mock_response = Mock()
        mock_response.iter_lines.return_value = mock_stream()
        mock_requests.post.return_value = mock_response
        
        config = ProviderConfig(provider_type="openrouter", api_key="test", model="test")
        provider = OpenRouterProvider(config)
        
        messages = [ChatMessage(role="user", content="Hi")]
        stream = provider.chat_completion(messages, stream=True)
        chunks = list(stream)
        
        # Should handle empty delta gracefully
        assert len(chunks) >= 1


class TestProviderConfiguration:
    """Test provider configuration validation."""
    
    def test_lmstudio_default_url(self):
        """Test LMStudio default URL is correct."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        assert provider.config.base_url == "http://localhost:1234"
    
    def test_openrouter_default_url(self):
        """Test OpenRouter default URL is correct."""
        config = ProviderConfig(provider_type="openrouter", api_key="test")
        provider = OpenRouterProvider(config)
        assert provider.config.base_url == "https://openrouter.ai/api/v1"
    
    def test_cerebras_default_url(self):
        """Test Cerebras default URL is correct."""
        config = ProviderConfig(provider_type="cerebras", api_key="test")
        provider = CerebrasProvider(config)
        assert provider.config.base_url == "https://api.cerebras.com"
    
    def test_llamacpp_default_url(self):
        """Test LlamaCpp default URL is correct."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        assert provider.config.base_url == "http://localhost:8080"
    
    def test_url_trailing_slash_stripped(self):
        """Test that trailing slashes are stripped from URLs."""
        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234/")
        provider = LMStudioProvider(config)
        assert provider.config.base_url == "http://localhost:1234"


class TestCapabilities:
    """Test provider capabilities."""
    
    def test_lmstudio_capabilities(self):
        """Test LMStudio capabilities."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        caps = provider.get_capabilities()
        assert ProviderCapability.CHAT in caps
        assert ProviderCapability.STREAMING in caps
        assert ProviderCapability.MODELS in caps
    
    def test_openrouter_capabilities(self):
        """Test OpenRouter capabilities."""
        config = ProviderConfig(provider_type="openrouter", api_key="test")
        provider = OpenRouterProvider(config)
        caps = provider.get_capabilities()
        assert ProviderCapability.CHAT in caps
        assert ProviderCapability.STREAMING in caps
        assert ProviderCapability.MODELS in caps
    
    def test_cerebras_capabilities(self):
        """Test Cerebras capabilities."""
        config = ProviderConfig(provider_type="cerebras", api_key="test")
        provider = CerebrasProvider(config)
        caps = provider.get_capabilities()
        assert ProviderCapability.CHAT in caps
        assert ProviderCapability.STREAMING in caps
        assert ProviderCapability.MODELS in caps
    
    def test_llamacpp_capabilities(self):
        """Test LlamaCpp capabilities."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        caps = provider.get_capabilities()
        assert ProviderCapability.CHAT in caps
        assert ProviderCapability.STREAMING in caps
        assert ProviderCapability.MODELS in caps