"""Tests for individual provider implementations."""

import pytest
from unittest.mock import Mock, patch
from app.providers import (
    LMStudioProvider,
    OpenRouterProvider,
    CerebrasProvider,
    LlamaCppProvider,
    ProviderConfig,
    ChatMessage,
    ChatResponse
)


class TestLMStudioProvider:
    """Test suite for LMStudioProvider."""
    
    def test_provider_initialization(self):
        """Test provider initialization with config."""
        config = ProviderConfig(
            provider_type='lmstudio',
            base_url='http://localhost:1234',
            model='test-model'
        )
        provider = LMStudioProvider(config)
        assert provider.provider_name == 'lmstudio'
        assert provider.config.base_url == 'http://localhost:1234'
        assert provider.config.model == 'test-model'
    
    def test_default_base_url(self):
        """Test default base URL is set."""
        config = ProviderConfig(provider_type='lmstudio')
        provider = LMStudioProvider(config)
        assert provider.config.base_url == 'http://localhost:1234'
    
    def test_config_schema(self):
        """Test configuration schema generation."""
        config = ProviderConfig(provider_type='lmstudio')
        provider = LMStudioProvider(config)
        schema = provider.get_config_schema()
        assert schema['provider_type'] == 'lmstudio'
        assert len(schema['fields']) > 0
        field_names = [f['name'] for f in schema['fields']]
        assert 'base_url' in field_names
    
    def test_supports_streaming(self):
        """Test that LM Studio supports streaming."""
        config = ProviderConfig(provider_type='lmstudio')
        provider = LMStudioProvider(config)
        assert provider.supports_streaming() is True
    
    def test_requires_api_key(self):
        """Test that LM Studio does not require API key."""
        config = ProviderConfig(provider_type='lmstudio')
        provider = LMStudioProvider(config)
        assert provider.requires_api_key() is False


class TestOpenRouterProvider:
    """Test suite for OpenRouterProvider."""
    
    def test_provider_initialization(self):
        """Test provider initialization."""
        config = ProviderConfig(
            provider_type='openrouter',
            api_key='test-key',
            model='openai/gpt-4o-mini'
        )
        provider = OpenRouterProvider(config)
        assert provider.provider_name == 'openrouter'
        assert provider.config.api_key == 'test-key'
    
    def test_missing_api_key_raises(self):
        """Test that missing API key raises error."""
        config = ProviderConfig(provider_type='openrouter')
        with pytest.raises(Exception):
            OpenRouterProvider(config)
    
    def test_config_schema(self):
        """Test configuration schema."""
        config = ProviderConfig(provider_type='openrouter')
        provider = OpenRouterProvider(config)
        schema = provider.get_config_schema()
        assert schema['provider_type'] == 'openrouter'
        field_names = [f['name'] for f in schema['fields']]
        assert 'api_key' in field_names
        assert 'model' in field_names
        assert 'thinking_budget' in field_names
    
    def test_supports_streaming(self):
        """Test that OpenRouter supports streaming."""
        config = ProviderConfig(provider_type='openrouter', api_key='test')
        provider = OpenRouterProvider(config)
        assert provider.supports_streaming() is True
    
    def test_requires_api_key(self):
        """Test that OpenRouter requires API key."""
        config = ProviderConfig(provider_type='openrouter', api_key='test')
        provider = OpenRouterProvider(config)
        assert provider.requires_api_key() is True


class TestCerebrasProvider:
    """Test suite for CerebrasProvider."""
    
    def test_provider_initialization(self):
        """Test provider initialization."""
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key',
            model='llama-3.3-70b-versatile'
        )
        provider = CerebrasProvider(config)
        assert provider.provider_name == 'cerebras'
        assert provider.config.api_key == 'test-key'
    
    def test_missing_api_key_raises(self):
        """Test that missing API key raises error."""
        config = ProviderConfig(provider_type='cerebras')
        with pytest.raises(Exception):
            CerebrasProvider(config)
    
    def test_config_schema(self):
        """Test configuration schema."""
        config = ProviderConfig(provider_type='cerebras')
        provider = CerebrasProvider(config)
        schema = provider.get_config_schema()
        assert schema['provider_type'] == 'cerebras'
        field_names = [f['name'] for f in schema['fields']]
        assert 'api_key' in field_names
        assert 'model' in field_names
    
    def test_supports_streaming(self):
        """Test that Cerebras supports streaming."""
        config = ProviderConfig(provider_type='cerebras', api_key='test')
        provider = CerebrasProvider(config)
        assert provider.supports_streaming() is True
    
    def test_requires_api_key(self):
        """Test that Cerebras requires API key."""
        config = ProviderConfig(provider_type='cerebras', api_key='test')
        provider = CerebrasProvider(config)
        assert provider.requires_api_key() is True


class TestLlamaCppProvider:
    """Test suite for LlamaCppProvider."""
    
    def test_provider_initialization(self):
        """Test provider initialization."""
        config = ProviderConfig(
            provider_type='llamacpp',
            base_url='http://localhost:8080',
            model='test-model.gguf'
        )
        provider = LlamaCppProvider(config)
        assert provider.provider_name == 'llamacpp'
        assert provider.config.base_url == 'http://localhost:8080'
    
    def test_default_base_url(self):
        """Test default base URL is set."""
        config = ProviderConfig(provider_type='llamacpp')
        provider = LlamaCppProvider(config)
        assert provider.config.base_url == 'http://localhost:8080'
    
    def test_config_schema(self):
        """Test configuration schema."""
        config = ProviderConfig(provider_type='llamacpp')
        provider = LlamaCppProvider(config)
        schema = provider.get_config_schema()
        assert schema['provider_type'] == 'llamacpp'
        field_names = [f['name'] for f in schema['fields']]
        assert 'base_url' in field_names
        assert 'model' in field_names
        assert 'auto_start' in field_names
    
    def test_supports_streaming(self):
        """Test that Llama.cpp supports streaming."""
        config = ProviderConfig(provider_type='llamacpp')
        provider = LlamaCppProvider(config)
        # Initially may not support streaming if server not running
        # but capability is listed
        caps = provider.get_capabilities()
        from app.providers.base import ProviderCapability
        assert ProviderCapability.STREAMING in caps
    
    def test_requires_api_key(self):
        """Test that Llama.cpp does not require API key."""
        config = ProviderConfig(provider_type='llamacpp')
        provider = LlamaCppProvider(config)
        assert provider.requires_api_key() is False


class TestChatMessage:
    """Test suite for ChatMessage dataclass."""
    
    def test_chat_message_creation(self):
        """Test creating a chat message."""
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.to_dict() == {"role": "user", "content": "Hello"}
    
    def test_chat_message_with_optional_fields(self):
        """Test chat message with optional fields."""
        msg = ChatMessage(
            role="assistant",
            content="Response",
            name="Bot",
            tool_calls=[{"id": "1", "type": "function"}]
        )
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Response"
        assert d["name"] == "Bot"
        assert d["tool_calls"] == [{"id": "1", "type": "function"}]


class TestChatResponse:
    """Test suite for ChatResponse dataclass."""
    
    def test_chat_response_creation(self):
        """Test creating a chat response."""
        resp = ChatResponse(
            content="Hello!",
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        assert resp.content == "Hello!"
        assert resp.model == "gpt-4"
        assert resp.usage == {"total_tokens": 100}
    
    def test_to_dict(self):
        """Test converting response to dict."""
        resp = ChatResponse(
            content="Test",
            model="test-model",
            thinking="Let me think...",
            usage={"prompt_tokens": 10, "completion_tokens": 20}
        )
        d = resp.to_dict()
        assert d["content"] == "Test"
        assert d["model"] == "test-model"
        assert d["thinking"] == "Let me think..."
        assert "usage" in d


class TestProviderConfig:
    """Test suite for ProviderConfig dataclass."""
    
    def test_provider_config_creation(self):
        """Test creating a provider config."""
        config = ProviderConfig(
            provider_type='test',
            api_key='secret',
            base_url='http://test.com',
            model='test-model',
            timeout=120
        )
        assert config.provider_type == 'test'
        assert config.api_key == 'secret'
        assert config.base_url == 'http://test.com'
        assert config.model == 'test-model'
        assert config.timeout == 120
    
    def test_to_dict_masks_api_key(self):
        """Test that to_dict masks the API key."""
        config = ProviderConfig(
            provider_type='test',
            api_key='longsecretkey123'
        )
        d = config.to_dict()
        assert d['api_key'] == '***key123'