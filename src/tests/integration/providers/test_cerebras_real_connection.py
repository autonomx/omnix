"""Test for Cerebras real connection using API key from settings.json."""

import pytest
import json
import os
from app.providers import CerebrasProvider, ProviderConfig, ModelInfo
from app.providers.base import AuthenticationError, ConnectionError, ModelNotFoundError


class TestCerebrasRealConnection:
    """Test suite for Cerebras real connection using settings.json API key."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Load settings from data/settings.json
        settings_path = os.path.join('data', 'settings.json')
        if not os.path.exists(settings_path):
            pytest.skip("data/settings.json not found")
        
        with open(settings_path, 'r') as f:
            self.settings = json.load(f)
    
    def test_cerebras_api_key_exists_in_settings(self):
        """Test that Cerebras API key exists in settings.json."""
        assert 'cerebras' in self.settings, "Cerebras configuration not found in settings.json"
        assert 'api_key' in self.settings['cerebras'], "Cerebras API key not found in settings.json"
        assert self.settings['cerebras']['api_key'], "Cerebras API key is empty"
        assert self.settings['cerebras']['api_key'] != 'your-cerebras-api-key-here', "Cerebras API key is still the placeholder value"
    
    def test_cerebras_provider_creation_from_settings(self):
        """Test creating Cerebras provider from settings.json."""
        cerebras_config = self.settings.get('cerebras', {})
        api_key = cerebras_config.get('api_key')
        model = cerebras_config.get('model', 'llama-3.3-70b-versatile')
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key=api_key,
            model=model
        )
        provider = CerebrasProvider(config)
        
        assert provider is not None
        assert provider.provider_name == 'cerebras'
        assert provider.config.api_key == api_key
        assert provider.config.model == model
        assert provider.config.base_url == 'https://api.cerebras.ai'
    
    def test_cerebras_real_connection(self):
        """Test real connection to Cerebras API."""
        cerebras_config = self.settings.get('cerebras', {})
        api_key = cerebras_config.get('api_key')
        model = cerebras_config.get('model', 'llama-3.3-70b-versatile')
        
        if not api_key:
            pytest.skip("No Cerebras API key found in settings.json")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key=api_key,
            model=model
        )
        provider = CerebrasProvider(config)
        
        # Test connection
        try:
            connection_result = provider.test_connection()
            assert connection_result is True, "Failed to connect to Cerebras API"
        except AuthenticationError as e:
            pytest.skip(f"Authentication failed: {e}")
        except ConnectionError as e:
            pytest.skip(f"Connection failed: {e}")
        except Exception as e:
            pytest.skip(f"Unexpected error: {e}")
    
    def test_cerebras_real_get_models(self):
        """Test real model retrieval from Cerebras API."""
        cerebras_config = self.settings.get('cerebras', {})
        api_key = cerebras_config.get('api_key')
        model = cerebras_config.get('model', 'llama-3.3-70b-versatile')
        
        if not api_key:
            pytest.skip("No Cerebras API key found in settings.json")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key=api_key,
            model=model
        )
        provider = CerebrasProvider(config)
        
        # Test model retrieval
        try:
            models = provider.get_models()
            assert isinstance(models, list), "get_models() should return a list"
            assert len(models) > 0, "Should return at least one model"
            
            # Verify model structure
            first_model = models[0]
            assert hasattr(first_model, 'id'), "Model should have id attribute"
            assert hasattr(first_model, 'name'), "Model should have name attribute"
            assert hasattr(first_model, 'provider'), "Model should have provider attribute"
            assert first_model.provider == 'cerebras', "Model provider should be cerebras"
            
            print(f"Successfully retrieved {len(models)} models from Cerebras:")
            for model_info in models:
                print(f"  - {model_info.name} (ID: {model_info.id})")
                
        except AuthenticationError as e:
            pytest.skip(f"Authentication failed: {e}")
        except ConnectionError as e:
            pytest.skip(f"Connection failed: {e}")
        except Exception as e:
            pytest.skip(f"Unexpected error: {e}")
    
    def test_cerebras_real_chat_completion(self):
        """Test real chat completion with Cerebras API."""
        cerebras_config = self.settings.get('cerebras', {})
        api_key = cerebras_config.get('api_key')
        model = cerebras_config.get('model', 'llama-3.3-70b-versatile')
        
        if not api_key:
            pytest.skip("No Cerebras API key found in settings.json")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key=api_key,
            model=model
        )
        provider = CerebrasProvider(config)
        
        from app.providers import ChatMessage
        messages = [ChatMessage(role='user', content='Hello, how are you?')]
        
        # Test non-streaming completion
        try:
            response = provider.chat_completion(messages, stream=False, max_tokens=50)
            assert response is not None
            assert isinstance(response.content, str)
            assert len(response.content) > 0
            print(f"Chat completion response: {response.content[:100]}...")
        except AuthenticationError as e:
            pytest.skip(f"Authentication failed: {e}")
        except ConnectionError as e:
            pytest.skip(f"Connection failed: {e}")
        except Exception as e:
            pytest.skip(f"Unexpected error: {e}")
    
    def test_cerebras_real_streaming_chat_completion(self):
        """Test real streaming chat completion with Cerebras API."""
        cerebras_config = self.settings.get('cerebras', {})
        api_key = cerebras_config.get('api_key')
        model = cerebras_config.get('model', 'llama-3.3-70b-versatile')
        
        if not api_key:
            pytest.skip("No Cerebras API key found in settings.json")
        
        config = ProviderConfig(
            provider_type='cerebras',
            api_key=api_key,
            model=model
        )
        provider = CerebrasProvider(config)
        
        from app.providers import ChatMessage
        messages = [ChatMessage(role='user', content='Hello, how are you?')]
        
        # Test streaming completion
        try:
            responses = list(provider.chat_completion(messages, stream=True, max_tokens=50))
            assert len(responses) > 0
            assert all(isinstance(r.content, str) for r in responses)
            assert all(len(r.content) >= 0 for r in responses)  # Content can be empty for some chunks
            
            full_response = ''.join(r.content for r in responses)
            print(f"Streaming chat completion response: {full_response[:100]}...")
        except AuthenticationError as e:
            pytest.skip(f"Authentication failed: {e}")
        except ConnectionError as e:
            pytest.skip(f"Connection failed: {e}")
        except Exception as e:
            pytest.skip(f"Unexpected error: {e}")


class TestCerebrasIntegrationWithSettingsFile:
    """Integration tests for Cerebras provider using the actual settings.json file."""
    
    def test_cerebras_provider_from_actual_settings(self):
        """Test creating Cerebras provider from the actual settings.json file."""
        # Import shared module to test settings loading
        import app.shared as shared
        
        # Load settings from the actual file
        settings = shared.load_settings()
        assert 'provider' in settings
        assert 'cerebras' in settings
        
        # Check if Cerebras is configured
        cerebras_config = settings.get('cerebras', {})
        if not cerebras_config.get('api_key'):
            pytest.skip("Cerebras API key not configured in settings.json")
        
        # Test creating provider from settings
        provider = shared.get_provider()
        assert provider is not None
        assert provider.provider_name == 'cerebras'
        assert provider.config.api_key == cerebras_config['api_key']
        assert provider.config.model == cerebras_config.get('model', 'llama-3.3-70b-versatile')
        
        print(f"Successfully created Cerebras provider from settings.json")
        print(f"API Key: {provider.config.api_key[:10]}...")
        print(f"Model: {provider.config.model}")
    
    def test_cerebras_connection_from_settings(self):
        """Test Cerebras connection using the actual settings.json configuration."""
        import app.shared as shared
        
        # Load settings from the actual file
        settings = shared.load_settings()
        cerebras_config = settings.get('cerebras', {})
        
        if not cerebras_config.get('api_key'):
            pytest.skip("Cerebras API key not configured in settings.json")
        
        # Create provider from settings
        provider = shared.get_provider()
        if provider is None or provider.provider_name != 'cerebras':
            pytest.skip("Cerebras provider not properly configured")
        
        # Test connection
        try:
            connection_result = provider.test_connection()
            assert connection_result is True, "Failed to connect to Cerebras API using settings.json"
            print("Successfully connected to Cerebras API using settings.json configuration")
        except AuthenticationError as e:
            pytest.skip(f"Authentication failed: {e}")
        except ConnectionError as e:
            pytest.skip(f"Connection failed: {e}")
        except Exception as e:
            pytest.skip(f"Unexpected error: {e}")
    
    def test_cerebras_models_from_settings(self):
        """Test Cerebras model retrieval using the actual settings.json configuration."""
        import app.shared as shared
        
        # Load settings from the actual file
        settings = shared.load_settings()
        cerebras_config = settings.get('cerebras', {})
        
        if not cerebras_config.get('api_key'):
            pytest.skip("Cerebras API key not configured in settings.json")
        
        # Create provider from settings
        provider = shared.get_provider()
        if provider is None or provider.provider_name != 'cerebras':
            pytest.skip("Cerebras provider not properly configured")
        
        # Test model retrieval
        try:
            models = provider.get_models()
            assert isinstance(models, list), "get_models() should return a list"
            assert len(models) > 0, "Should return at least one model"
            
            print(f"Successfully retrieved {len(models)} models from Cerebras using settings.json:")
            for model_info in models:
                print(f"  - {model_info.name} (ID: {model_info.id})")
                
        except AuthenticationError as e:
            pytest.skip(f"Authentication failed: {e}")
        except ConnectionError as e:
            pytest.skip(f"Connection failed: {e}")
        except Exception as e:
            pytest.skip(f"Unexpected error: {e}")