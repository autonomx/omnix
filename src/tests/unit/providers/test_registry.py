"""Tests for the Provider Registry."""

import pytest
from app.providers import ProviderRegistry, get_registry, list_available_providers
from app.providers.base import BaseProvider, ProviderConfig


class TestProviderRegistry:
    """Test suite for ProviderRegistry."""
    
    def test_registry_singleton(self):
        """Test that get_registry returns the same instance."""
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2
    
    def test_discover_providers(self):
        """Test provider discovery."""
        registry = ProviderRegistry()
        registry.discover_providers()
        providers = registry.list_providers()
        
        # Should discover at least the built-in providers
        provider_names = [p['name'] for p in providers]
        assert 'lmstudio' in provider_names
        assert 'openrouter' in provider_names
        assert 'cerebras' in provider_names
        assert 'llamacpp' in provider_names
    
    def test_get_provider_class(self):
        """Test getting provider class by name."""
        registry = get_registry()
        lmstudio_class = registry.get_provider_class('lmstudio')
        assert lmstudio_class is not None
        assert issubclass(lmstudio_class, BaseProvider)
        assert lmstudio_class.provider_name == 'lmstudio'
    
    def test_create_provider(self):
        """Test creating a provider instance."""
        registry = get_registry()
        config = ProviderConfig(
            provider_type='lmstudio',
            base_url='http://localhost:1234'
        )
        provider = registry.create_provider('lmstudio', provider_config=config)
        assert provider is not None
        assert isinstance(provider, BaseProvider)
        assert provider.provider_name == 'lmstudio'
        assert provider.config.base_url == 'http://localhost:1234'
    
    def test_create_provider_with_dict(self):
        """Test creating a provider using a dictionary config."""
        registry = get_registry()
        config_dict = {
            'base_url': 'http://localhost:1234',
            'model': 'test-model'
        }
        provider = registry.create_provider('lmstudio', config=config_dict)
        assert provider is not None
        assert provider.config.base_url == 'http://localhost:1234'
        assert provider.config.model == 'test-model'
    
    def test_create_nonexistent_provider(self):
        """Test creating a provider that doesn't exist."""
        registry = get_registry()
        provider = registry.create_provider('nonexistent')
        assert provider is None
    
    def test_register_unregister_provider(self):
        """Test manual registration and unregistration."""
        from app.providers.base import BaseProvider
        
        class TestProvider(BaseProvider):
            provider_name = "test"
            provider_display_name = "Test Provider"
            provider_description = "A test provider"
            
            def chat_completion(self, messages, model=None, stream=False, **kwargs):
                pass
            
            def get_models(self):
                pass
            
            def test_connection(self):
                return True
        
        registry = ProviderRegistry()
        registry.clear()
        
        # Should not be registered initially
        assert registry.get_provider_class('test') is None
        
        # Register the provider
        registry.register_provider(TestProvider)
        assert registry.get_provider_class('test') == TestProvider
        
        # Unregister
        result = registry.unregister_provider('test')
        assert result is True
        assert registry.get_provider_class('test') is None
        
        # Unregister non-existent provider
        result = registry.unregister_provider('nonexistent')
        assert result is False
    
    def test_list_providers_metadata(self):
        """Test that provider metadata is correctly retrieved."""
        registry = get_registry()
        providers = registry.list_providers()
        
        for provider in providers:
            assert 'name' in provider
            assert 'display_name' in provider
            assert 'description' in provider
            assert 'capabilities' in provider
            assert isinstance(provider['capabilities'], list)


class TestListAvailableProviders:
    """Test the convenience function list_available_providers."""
    
    def test_list_returns_providers(self):
        """Test that list_available_providers returns a list."""
        providers = list_available_providers()
        assert isinstance(providers, list)
        assert len(providers) > 0
    
    def test_contains_builtin_providers(self):
        """Test that built-in providers are listed."""
        providers = list_available_providers()
        names = [p['name'] for p in providers]
        assert 'lmstudio' in names
        assert 'openrouter' in names
        assert 'cerebras' in names
        assert 'llamacpp' in names