"""Test for Cerebras model status and connection using settings.json API key."""

import os
from unittest.mock import Mock, patch

import pytest
import requests

from app.providers import CerebrasProvider, ModelInfo, ProviderConfig
from app.providers.base import AuthenticationError, ConnectionError


class TestCerebrasModelStatus:
    """Test suite for Cerebras model status and connection functionality."""
    
    def test_cerebras_provider_initialization_with_valid_config(self):
        """Test Cerebras provider initialization with valid configuration."""
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-api-key',
            model='llama-3.3-70b-versatile'
        )
        provider = CerebrasProvider(config)
        
        assert provider.provider_name == 'cerebras'
        assert provider.config.api_key == 'test-api-key'
        assert provider.config.model == 'llama-3.3-70b-versatile'
        assert provider.config.base_url == 'https://api.cerebras.ai'
    
    def test_cerebras_provider_initialization_without_api_key_raises_error(self):
        """Test that Cerebras provider raises error when API key is missing."""
        config = ProviderConfig(provider_type='cerebras')
        with pytest.raises(AuthenticationError, match="Cerebras requires an API key"):
            CerebrasProvider(config)
    
    def test_cerebras_provider_initialization_with_custom_base_url(self):
        """Test Cerebras provider with custom base URL."""
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key',
            base_url='https://custom.cerebras.ai'
        )
        provider = CerebrasProvider(config)
        assert provider.config.base_url == 'https://custom.cerebras.ai'
    
    def test_cerebras_config_schema(self):
        """Test Cerebras provider configuration schema."""
        config = ProviderConfig(provider_type='cerebras', api_key='test-key')
        provider = CerebrasProvider(config)
        schema = provider.get_config_schema()
        
        assert schema['provider_type'] == 'cerebras'
        assert schema['display_name'] == 'Cerebras'
        assert schema['description'] == 'Cerebras Cloud API with access to their LLM models'
        
        fields = schema['fields']
        field_names = [f['name'] for f in fields]
        assert 'api_key' in field_names
        assert 'model' in field_names
        
        # Check api_key field properties
        api_key_field = next(f for f in fields if f['name'] == 'api_key')
        assert api_key_field['type'] == 'password'
        assert api_key_field['required'] is True
        assert 'Cerebras API key' in api_key_field['description']
    
    def test_cerebras_supports_streaming(self):
        """Test that Cerebras provider supports streaming."""
        config = ProviderConfig(provider_type='cerebras', api_key='test')
        provider = CerebrasProvider(config)
        assert provider.supports_streaming() is True
    
    def test_cerebras_requires_api_key(self):
        """Test that Cerebras provider requires API key."""
        config = ProviderConfig(provider_type='cerebras', api_key='test')
        provider = CerebrasProvider(config)
        assert provider.requires_api_key() is True
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_test_connection_success(self, mock_request):
        """Test successful connection to Cerebras API."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='valid-api-key'
        )
        provider = CerebrasProvider(config)
        
        result = provider.test_connection()
        assert result is True
        
        # Verify the request was made correctly
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'get'  # HTTP method
        assert call_args[0][1] == 'https://api.cerebras.ai/v1/models'  # URL
        headers = call_args[1]['headers']
        assert headers['Authorization'] == 'Bearer valid-api-key'
        assert headers['Content-Type'] == 'application/json'
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_test_connection_authentication_error(self, mock_request):
        """Test connection failure due to authentication error."""
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "Authentication failed", response=mock_response
        )
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='invalid-api-key'
        )
        provider = CerebrasProvider(config)
        
        with pytest.raises(AuthenticationError, match="Authentication failed"):
            provider.test_connection()
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_test_connection_connection_error(self, mock_request):
        """Test connection failure due to network error."""
        # An unavailable connection is reported as an unsuccessful probe.
        mock_request.side_effect = requests.ConnectionError("Connection failed")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key'
        )
        provider = CerebrasProvider(config)
        
        assert provider.test_connection() is False
        assert mock_request.call_count == 2
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_get_models_success(self, mock_request):
        """Test successful retrieval of models from Cerebras."""
        # Mock successful response with models
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [
                {
                    'id': 'llama-3.3-70b-versatile',
                    'name': 'Llama 3.3 70B Versatile',
                    'owned_by': 'cerebras',
                    'context_length': 128000,
                    'description': 'General-purpose model'
                },
                {
                    'id': 'llama-3.1-8b-instruct',
                    'name': 'Llama 3.1 8B Instruct',
                    'owned_by': 'cerebras',
                    'context_length': 128000,
                    'description': 'Instruction-tuned model'
                }
            ]
        }
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key'
        )
        provider = CerebrasProvider(config)
        
        models = provider.get_models()
        
        assert len(models) == 2
        assert isinstance(models[0], ModelInfo)
        assert models[0].id == 'llama-3.3-70b-versatile'
        assert models[0].name == 'Llama 3.3 70B Versatile'
        assert models[0].provider == 'cerebras'
        assert models[0].context_length == 128000
        assert models[0].description == 'General-purpose model'
        
        # Verify the request was made correctly
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'get'  # HTTP method
        assert call_args[0][1] == 'https://api.cerebras.ai/v1/models'  # URL
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_get_models_empty_response(self, mock_request):
        """Test handling of empty models response."""
        # Mock response with empty data
        mock_response = Mock()
        mock_response.json.return_value = {'data': []}
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key'
        )
        provider = CerebrasProvider(config)
        
        models = provider.get_models()
        assert models == []
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_get_models_invalid_json(self, mock_request):
        """Test handling of invalid JSON response."""
        # Mock response that raises JSON decode error
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key'
        )
        provider = CerebrasProvider(config)
        
        with pytest.raises(ConnectionError, match="Failed to fetch models from Cerebras: Invalid JSON"):
            provider.get_models()
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_get_models_authentication_error(self, mock_request):
        """Test handling of authentication error when fetching models."""
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "Authentication failed", response=mock_response
        )
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='invalid-key'
        )
        provider = CerebrasProvider(config)
        
        with pytest.raises(AuthenticationError, match="Authentication failed"):
            provider.get_models()
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_chat_completion_non_streaming(self, mock_request):
        """Test non-streaming chat completion."""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'Hello! How can I help you?',
                    'reasoning': 'Analyzing user request...'
                },
                'finish_reason': 'stop'
            }],
            'model': 'llama-3.3-70b-versatile',
            'usage': {'total_tokens': 15}
        }
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key',
            model='llama-3.3-70b-versatile'
        )
        provider = CerebrasProvider(config)
        
        from app.providers import ChatMessage
        messages = [ChatMessage(role='user', content='Hello')]
        
        response = provider.chat_completion(messages, stream=False)
        
        assert response.content == 'Hello! How can I help you?'
        assert response.model == 'llama-3.3-70b-versatile'
        assert response.thinking == 'Analyzing user request...'
        assert response.finish_reason == 'stop'
        assert response.usage == {'total_tokens': 15}
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_chat_completion_streaming(self, mock_request):
        """Test streaming chat completion."""
        # Mock streaming response
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b'data: {"choices":[{"delta":{"content":"!"}}]}',
            b'data: [DONE]'
        ]
        mock_request.return_value = mock_response
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key',
            model='llama-3.3-70b-versatile'
        )
        provider = CerebrasProvider(config)
        
        from app.providers import ChatMessage
        messages = [ChatMessage(role='user', content='Hello')]
        
        responses = list(provider.chat_completion(messages, stream=True))
        
        assert len(responses) == 2
        assert responses[0].content == 'Hello'
        assert responses[1].content == '!'
    
    def test_cerebras_make_request_with_authorization(self):
        """Test that _make_request adds proper authorization headers."""
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-api-key'
        )
        provider = CerebrasProvider(config)
        
        with patch('app.providers.cerebras_provider.requests.request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response
            
            provider._make_request('get', '/test/endpoint')
            
            # Verify authorization header was added
            call_args = mock_request.call_args
            headers = call_args[1]['headers']
            assert headers['Authorization'] == 'Bearer test-api-key'
            assert headers['Content-Type'] == 'application/json'
    
    def test_cerebras_make_request_connection_error_handling(self):
        """Test that _make_request properly handles connection errors."""
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key'
        )
        provider = CerebrasProvider(config)
        
        with patch('app.providers.cerebras_provider.requests.request') as mock_request:
            mock_request.side_effect = requests.ConnectionError("Connection failed")
            
            with pytest.raises(ConnectionError, match="Failed to connect to Cerebras"):
                provider._make_request('get', '/test/endpoint')
    
    def test_cerebras_make_request_timeout_handling(self):
        """Test that _make_request properly handles timeout errors."""
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key'
        )
        provider = CerebrasProvider(config)
        
        with patch('app.providers.cerebras_provider.requests.request') as mock_request:
            mock_request.side_effect = requests.Timeout("Timeout")
            
            with pytest.raises(ConnectionError, match="Connection to Cerebras timed out"):
                provider._make_request('get', '/test/endpoint', timeout=5)


class TestCerebrasProviderServiceSettings:
    """Provider construction uses typed settings and the secret-store port."""

    def _install(self, monkeypatch, settings, secrets):
        from app.providers import service as provider_service

        monkeypatch.setattr(provider_service, "load_settings", lambda: settings)
        monkeypatch.setattr(provider_service, "load_secrets", lambda: secrets)
        provider_service.invalidate_provider_cache()
        return provider_service

    def test_provider_uses_settings_and_secret_store(self, monkeypatch):
        settings = {
            "provider": "cerebras",
            "cerebras": {"model": "llama-3.3-70b-versatile"},
        }
        provider_service = self._install(
            monkeypatch,
            settings,
            {"api_keys": {"cerebras": "test-api-key-from-secret-store"}},
        )

        provider = provider_service.get_provider()

        assert provider is not None
        assert provider.provider_name == "cerebras"
        assert provider.config.api_key == "test-api-key-from-secret-store"
        assert provider.config.model == "llama-3.3-70b-versatile"

    def test_missing_secret_does_not_read_a_fallback_file(self, monkeypatch):
        from app.providers.exceptions import ProviderRegistrationError

        provider_service = self._install(
            monkeypatch,
            {"provider": "cerebras", "cerebras": {"model": "llama-3.3-70b-versatile"}},
            {"api_keys": {}},
        )

        with pytest.raises(ProviderRegistrationError, match="Cerebras requires an API key"):
            provider_service.get_provider()

    def test_empty_settings_use_kernel_defaults(self, monkeypatch):
        provider_service = self._install(monkeypatch, {}, {"api_keys": {}})

        provider = provider_service.get_provider()

        assert provider is not None
        assert provider.provider_name == "lmstudio"


class TestCerebrasModelStatusEndToEnd:
    """End-to-end tests for Cerebras model status functionality."""
    
    @pytest.mark.skipif(
        not os.environ.get('CEREBRAS_API_KEY'),
        reason="CEREBRAS_API_KEY not set in environment"
    )
    def test_cerebras_real_connection_and_models(self):
        """Test real connection to Cerebras API and model retrieval."""
        api_key = os.environ.get('CEREBRAS_API_KEY')
        if not api_key:
            pytest.skip("CEREBRAS_API_KEY not available for real API test")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key=api_key,
            model='llama-3.3-70b-versatile'
        )
        provider = CerebrasProvider(config)
        
        # Test connection
        connection_result = provider.test_connection()
        assert connection_result is True, "Failed to connect to Cerebras API"
        
        # Test model retrieval
        models = provider.get_models()
        assert isinstance(models, list), "get_models() should return a list"
        assert len(models) > 0, "Should return at least one model"
        
        # Verify model structure
        first_model = models[0]
        assert hasattr(first_model, 'id'), "Model should have id attribute"
        assert hasattr(first_model, 'name'), "Model should have name attribute"
        assert hasattr(first_model, 'provider'), "Model should have provider attribute"
        assert first_model.provider == 'cerebras', "Model provider should be cerebras"
    
    @pytest.mark.skipif(
        not os.environ.get('CEREBRAS_API_KEY'),
        reason="CEREBRAS_API_KEY not set in environment"
    )
    def test_cerebras_real_chat_completion(self):
        """Test real chat completion with Cerebras API."""
        api_key = os.environ.get('CEREBRAS_API_KEY')
        if not api_key:
            pytest.skip("CEREBRAS_API_KEY not available for real API test")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key=api_key,
            model='llama-3.3-70b-versatile'
        )
        provider = CerebrasProvider(config)
        
        from app.providers import ChatMessage
        messages = [ChatMessage(role='user', content='Hello, how are you?')]
        
        # Test non-streaming completion
        response = provider.chat_completion(messages, stream=False, max_tokens=50)
        assert response is not None
        assert isinstance(response.content, str)
        assert len(response.content) > 0
        
        # Test streaming completion
        responses = list(provider.chat_completion(messages, stream=True, max_tokens=50))
        assert len(responses) > 0
        assert all(isinstance(r.content, str) for r in responses)
        assert all(len(r.content) >= 0 for r in responses)  # Content can be empty for some chunks
