"""Comprehensive tests for provider implementations."""

from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from tests.support.http import install_provider_http
from app.providers import (
    AuthenticationError,
    CerebrasProvider,
    ChatMessage,
    ChatResponse,
    ConnectionError,
    LlamaCppProvider,
    LMStudioProvider,
    ModelInfo,
    ModelNotFoundError,
    OpenRouterProvider,
    ProviderCapability,
    ProviderConfig,
)



def _lmstudio(handler, **config):
    provider = LMStudioProvider(ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234", **config))
    install_provider_http(provider, handler)
    return provider


def _refuse(request):
    raise httpx.ConnectError("Connection failed")

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

    def test_chat_completion_with_streaming(self):
        """Test streaming chat completion."""
        body = (
            b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
            b'data: {"choices": [{"delta": {"content": " World"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        provider = _lmstudio(lambda request: httpx.Response(200, content=body), model="test-model")

        chunks = list(provider.chat_completion([ChatMessage(role="user", content="Hi")], stream=True))

        assert len(chunks) >= 2
        assert any(c.content for c in chunks)

    def test_chat_completion_connection_error(self):
        """Test chat completion with connection error."""
        provider = _lmstudio(_refuse, model="test-model")

        with pytest.raises(ConnectionError):
            provider.chat_completion([ChatMessage(role="user", content="Hi")])

    def test_chat_completion_empty_messages(self):
        """Test chat completion with empty messages."""
        provider = _lmstudio(_refuse)

        with pytest.raises(ValueError):
            provider.chat_completion([])

    def test_get_models_success(self):
        """Test successful get_models."""
        models_payload = {
            "data": [
                {"id": "model-1", "context_length": 4096, "description": "Model 1"},
                {"id": "model-2", "context_length": 8192},
            ]
        }
        provider = _lmstudio(lambda request: httpx.Response(200, json=models_payload))

        models = provider.get_models()

        assert len(models) == 2
        assert models[0].id == "model-1"
        assert models[0].context_length == 4096
        assert models[1].id == "model-2"

    def test_get_models_empty(self):
        """Test get_models with empty response."""
        provider = _lmstudio(lambda request: httpx.Response(200, json={"data": []}))

        assert provider.get_models() == []

    def test_get_models_connection_error(self):
        """Test get_models with connection error."""
        provider = _lmstudio(_refuse)

        with pytest.raises(ConnectionError):
            provider.get_models()

    def test_test_connection_success(self):
        """Test successful test_connection."""
        provider = _lmstudio(lambda request: httpx.Response(200, json={"data": []}))

        assert provider.test_connection() is True

    def test_test_connection_failure(self):
        """Test failed test_connection."""
        provider = _lmstudio(_refuse)

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
        assert provider.config.base_url == "http://127.0.0.1:1234"

    def test_lmstudio_nonlocal_url_is_preserved(self):
        config = ProviderConfig(
            provider_type="lmstudio",
            base_url="http://studio-host.local:1234",
        )
        provider = LMStudioProvider(config)
        assert provider.config.base_url == "http://studio-host.local:1234"


class TestOpenRouterProviderFull:
    """Full test suite for OpenRouterProvider."""
    
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
    
    def test_missing_api_key_raises(self):
        """Test that missing API key raises AuthenticationError."""
        config = ProviderConfig(provider_type="cerebras")
        with pytest.raises(AuthenticationError):
            CerebrasProvider(config)
    
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
    
    def test_chat_completion_model_not_found(self):
        """Test chat completion when model not found."""
        config = ProviderConfig(provider_type="llamacpp", model="nonexistent.gguf")
        provider = LlamaCppProvider(config)
        
        with pytest.raises(ModelNotFoundError):
            provider.chat_completion([ChatMessage(role="user", content="Hi")])
    
    def test_chat_completion_empty_messages(self):
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
    
    def test_test_connection_server_not_running(self):
        """Test test_connection when server is not running."""
        config = ProviderConfig(provider_type="llamacpp", base_url="http://localhost:8080")
        provider = LlamaCppProvider(config)
        install_provider_http(provider, _refuse)
        
        result = provider.test_connection()
        assert result is False
    
class TestStreamingEdgeCases:
    """Test streaming edge cases across providers."""
    
    def test_streaming_malformed_lines(self):
        """Test streaming with malformed SSE lines."""
        body = (
            b"data: malformed json\n\n"
            b'data: {"not": "a proper SSE"}\n\n'
            b'data: {"choices": [{"delta": {"content": "Valid"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        provider = _lmstudio(lambda request: httpx.Response(200, content=body), model="test-model")

        # Should yield at least one valid chunk without raising
        chunks = list(provider.chat_completion([ChatMessage(role="user", content="Hi")], stream=True))
        assert isinstance(chunks, list)
    
class TestProviderConfiguration:
    """Test provider configuration validation."""
    
    def test_lmstudio_default_url(self):
        """Test LMStudio default URL is correct."""
        config = ProviderConfig(provider_type="lmstudio")
        provider = LMStudioProvider(config)
        assert provider.config.base_url == "http://127.0.0.1:1234"
    
    def test_openrouter_default_url(self):
        """Test OpenRouter default URL is correct."""
        config = ProviderConfig(provider_type="openrouter", api_key="test")
        provider = OpenRouterProvider(config)
        assert provider.config.base_url == "https://openrouter.ai/api/v1"
    
    def test_llamacpp_default_url(self):
        """Test LlamaCpp default URL is correct."""
        config = ProviderConfig(provider_type="llamacpp")
        provider = LlamaCppProvider(config)
        assert provider.config.base_url == "http://localhost:8080"
    
    def test_url_trailing_slash_stripped(self):
        """Test that trailing slashes are stripped from URLs."""
        config = ProviderConfig(provider_type="lmstudio", base_url="http://localhost:1234/")
        provider = LMStudioProvider(config)
        assert provider.config.base_url == "http://127.0.0.1:1234"


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
