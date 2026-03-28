"""Test for Cerebras model status and connection using settings.json API key."""

import pytest
import json
import os
import tempfile
from unittest.mock import patch, Mock, MagicMock
from app.providers import CerebrasProvider, ProviderConfig, ModelInfo
from app.providers.base import AuthenticationError, ConnectionError, ModelNotFoundError


class TestCerebrasModelStatus:
    """Test suite for Cerebras model status and connection functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Create a temporary settings file for testing
        self.temp_settings_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.temp_settings_path = self.temp_settings_file.name
        self.temp_settings_file.close()
        
        # Store original settings path
        self.original_settings_path = os.environ.get('SETTINGS_FILE_PATH')
    
    def teardown_method(self):
        """Cleanup after each test method."""
        # Clean up temporary file
        if os.path.exists(self.temp_settings_path):
            os.unlink(self.temp_settings_path)
        
        # Restore original settings path
        if self.original_settings_path:
            os.environ['SETTINGS_FILE_PATH'] = self.original_settings_path
        elif 'SETTINGS_FILE_PATH' in os.environ:
            del os.environ['SETTINGS_FILE_PATH']
    
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
        mock_response.raise_for_status.side_effect = Exception("Authentication failed")
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
        # Mock connection error
        mock_request.side_effect = Exception("Connection failed")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key='test-key'
        )
        provider = CerebrasProvider(config)
        
        with pytest.raises(ConnectionError, match="Failed to connect to Cerebras"):
            provider.test_connection()
    
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
        
        with pytest.raises(ConnectionError, match="Invalid JSON response"):
            provider.get_models()
    
    @patch('app.providers.cerebras_provider.requests.request')
    def test_cerebras_get_models_authentication_error(self, mock_request):
        """Test handling of authentication error when fetching models."""
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Authentication failed")
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
            mock_request.side_effect = Exception("Connection failed")
            
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
            mock_request.side_effect = Exception("Timeout")
            
            with pytest.raises(ConnectionError, match="Connection to Cerebras timed out"):
                provider._make_request('get', '/test/endpoint', timeout=5)


class TestCerebrasIntegrationWithSettings:
    """Integration tests for Cerebras provider using settings.json."""
    
    def setup_method(self):
        """Setup for integration tests."""
        # Create a temporary settings file
        self.temp_settings_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.temp_settings_path = self.temp_settings_file.name
        self.temp_settings_file.close()
        
        # Store original environment
        self.original_env = os.environ.get('SETTINGS_FILE_PATH')
        os.environ['SETTINGS_FILE_PATH'] = self.temp_settings_path
    
    def teardown_method(self):
        """Cleanup after integration tests."""
        # Clean up temporary file
        if os.path.exists(self.temp_settings_path):
            os.unlink(self.temp_settings_path)
        
        # Restore original environment
        if self.original_env:
            os.environ['SETTINGS_FILE_PATH'] = self.original_env
        elif 'SETTINGS_FILE_PATH' in os.environ:
            del os.environ['SETTINGS_FILE_PATH']
    
    def test_cerebras_provider_from_settings(self):
        """Test creating Cerebras provider from settings.json."""
        # Create test settings
        test_settings = {
            'provider': 'cerebras',
            'cerebras': {
                'api_key': 'test-api-key-from-settings',
                'model': 'llama-3.3-70b-versatile'
            }
        }
        
        with open(self.temp_settings_path, 'w') as f:
            json.dump(test_settings, f)
        
        # Import shared module to test settings loading
        import app.shared as shared
        
        # Mock the load_settings function to use our test file
        with patch.object(shared, 'SETTINGS_FILE', self.temp_settings_path):
            settings = shared.load_settings()
            assert settings['provider'] == 'cerebras'
            assert settings['cerebras']['api_key'] == 'test-api-key-from-settings'
            assert settings['cerebras']['model'] == 'llama-3.3-70b-versatile'
            
            # Test creating provider from settings
            provider = shared.get_provider()
            assert provider is not None
            assert provider.provider_name == 'cerebras'
            assert provider.config.api_key == 'test-api-key-from-settings'
            assert provider.config.model == 'llama-3.3-70b-versatile'
    
    def test_cerebras_provider_with_missing_api_key_in_settings(self):
        """Test handling of missing API key in settings.json."""
        # Create test settings without API key
        test_settings = {
            'provider': 'cerebras',
            'cerebras': {
                'model': 'llama-3.3-70b-versatile'
                # Missing api_key
            }
        }
        
        with open(self.temp_settings_path, 'w') as f:
            json.dump(test_settings, f)
        
        import app.shared as shared
        
        with patch.object(shared, 'SETTINGS_FILE', self.temp_settings_path):
            # This should not raise an error during provider creation
            # but the provider should be None or handle the missing key gracefully
            provider = shared.get_provider()
            # The exact behavior depends on the implementation, but it should not crash
            assert provider is None or provider.config.api_key == ''
    
    def test_cerebras_provider_with_empty_settings(self):
        """Test Cerebras provider with empty settings.json."""
        # Create empty settings
        test_settings = {}
        
        with open(self.temp_settings_path, 'w') as f:
            json.dump(test_settings, f)
        
        import app.shared as shared
        
        with patch.object(shared, 'SETTINGS_FILE', self.temp_settings_path):
            settings = shared.load_settings()
            # Should return default settings
            assert 'provider' in settings
            assert 'cerebras' in settings
            
            # Creating provider should work but may not be functional
            provider = shared.get_provider()
            assert provider is not None
            assert provider.provider_name == 'cerebras'


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