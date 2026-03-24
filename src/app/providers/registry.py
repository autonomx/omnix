"""
Provider Registry - Dynamic plugin discovery and management system.

This module implements a registry that automatically discovers provider plugins
in the providers directory and provides a factory for creating provider instances.
"""

import os
import sys
import importlib
import inspect
from typing import Dict, Type, Optional, List, Any
from pathlib import Path

from .base import BaseProvider, ProviderConfig
from .exceptions import ProviderRegistrationError


class ProviderRegistry:
    """
    Registry for provider plugins.
    
    Handles automatic discovery of provider classes in the providers package,
    registration, and factory-based instantiation.
    """
    
    def __init__(self):
        """Initialize the provider registry."""
        self._providers: Dict[str, Type[BaseProvider]] = {}
        self._discovered = False
        
    def discover_providers(self) -> None:
        """
        Auto-discover provider classes from the providers package.
        
        Scans all .py files in the providers directory (excluding base and registry)
        and registers any classes that inherit from BaseProvider.
        """
        if self._discovered:
            return
            
        providers_dir = Path(__file__).parent
        self._providers = {}
        
        # Import all Python modules in the providers package
        for module_file in providers_dir.glob("*.py"):
            module_name = module_file.stem
            
            # Skip these files
            if module_name in ["__init__", "base", "registry", "exceptions"]:
                continue
                
            try:
                # Import the module
                full_module_name = f"app.providers.{module_name}"
                module = importlib.import_module(full_module_name)
                
                # Find all classes that inherit from BaseProvider
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseProvider) and 
                        obj != BaseProvider and 
                        obj.__module__ == full_module_name):
                        
                        provider_name = obj.provider_name
                        if provider_name in self._providers:
                            print(f"Warning: Provider '{provider_name}' already registered, overwriting")
                        self._providers[provider_name] = obj
                        print(f"Registered provider: {provider_name}")
                        
            except Exception as e:
                print(f"Error discovering provider in {module_name}: {e}")
                
        self._discovered = True
        print(f"Provider discovery complete. {len(self._providers)} providers available")
    
    def register_provider(self, provider_class: Type[BaseProvider]) -> None:
        """
        Manually register a provider class.
        
        Args:
            provider_class: Provider class inheriting from BaseProvider
            
        Raises:
            ProviderRegistrationError: If provider name is invalid or already registered
        """
        if not issubclass(provider_class, BaseProvider):
            raise ProviderRegistrationError(f"{provider_class.__name__} must inherit from BaseProvider")
            
        provider_name = provider_class.provider_name
        if not provider_name or provider_name == "base":
            raise ProviderRegistrationError(f"Invalid provider name: {provider_name}")
            
        if provider_name in self._providers:
            raise ProviderRegistrationError(f"Provider '{provider_name}' is already registered")
            
        self._providers[provider_name] = provider_class
        print(f"Manually registered provider: {provider_name}")
    
    def unregister_provider(self, provider_name: str) -> bool:
        """
        Unregister a provider.
        
        Args:
            provider_name: Name of the provider to unregister
            
        Returns:
            True if provider was unregistered, False if not found
        """
        if provider_name in self._providers:
            del self._providers[provider_name]
            print(f"Unregistered provider: {provider_name}")
            return True
        return False
    
    def get_provider_class(self, provider_name: str) -> Optional[Type[BaseProvider]]:
        """
        Get the provider class for a given provider name.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            Provider class or None if not found
        """
        if not self._discovered:
            self.discover_providers()
        return self._providers.get(provider_name)
    
    def list_providers(self) -> List[Dict[str, Any]]:
        """
        Get list of all registered providers with metadata.
        
        Returns:
            List of dictionaries with provider information
        """
        if not self._discovered:
            self.discover_providers()
            
        providers_list = []
        for name, provider_class in self._providers.items():
            # Create a temporary instance to get metadata (without config for now)
            try:
                # Get class-level attributes
                info = {
                    "name": name,
                    "display_name": getattr(provider_class, "provider_display_name", name),
                    "description": getattr(provider_class, "provider_description", ""),
                    "capabilities": [c.value for c in getattr(provider_class, "default_capabilities", [])],
                }
                providers_list.append(info)
            except Exception as e:
                print(f"Error getting info for provider {name}: {e}")
                
        return providers_list
    
    def create_provider(
        self,
        provider_name: str,
        config: Optional[Dict[str, Any]] = None,
        provider_config: Optional[ProviderConfig] = None
    ) -> Optional[BaseProvider]:
        """
        Factory method to create a provider instance.
        
        Args:
            provider_name: Name of the provider to instantiate
            config: Dictionary with configuration (alternative to provider_config)
            provider_config: ProviderConfig instance (preferred)
            
        Returns:
            Provider instance or None if provider not found
            
        Raises:
            ProviderRegistrationError: If provider class can't be instantiated
        """
        if not self._discovered:
            self.discover_providers()
            
        provider_class = self._providers.get(provider_name)
        if not provider_class:
            print(f"Provider '{provider_name}' not found")
            return None
            
        # Build ProviderConfig
        if provider_config:
            final_config = provider_config
        elif config:
            final_config = ProviderConfig(
                provider_type=provider_name,
                api_key=config.get("api_key"),
                base_url=config.get("base_url"),
                model=config.get("model"),
                timeout=config.get("timeout", 300),
                max_retries=config.get("max_retries", 3),
                extra_params=config.get("extra_params", {})
            )
        else:
            # Use empty config, provider should provide defaults
            final_config = ProviderConfig(provider_type=provider_name)
            
        try:
            provider_instance = provider_class(config=final_config)
            return provider_instance
        except Exception as e:
            raise ProviderRegistrationError(
                f"Failed to instantiate provider '{provider_name}': {e}"
            ) from e
    
    def clear(self) -> None:
        """Clear all registered providers (useful for testing)."""
        self._providers.clear()
        self._discovered = False


# Global registry instance
_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """
    Get the global provider registry instance.
    
    Returns:
        ProviderRegistry singleton
    """
    return _registry


# Convenience functions
def get_provider(provider_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[BaseProvider]:
    """
    Convenience function to get a provider instance.
    
    Args:
        provider_name: Name of the provider
        config: Optional configuration dictionary
        
    Returns:
        Provider instance or None
    """
    return get_registry().create_provider(provider_name, config)


def list_available_providers() -> List[Dict[str, Any]]:
    """
    Get list of all available providers.
    
    Returns:
        List of provider metadata dictionaries
    """
    return get_registry().list_providers()


def register_provider(provider_class: Type[BaseProvider]) -> None:
    """
    Register a provider class with the global registry.
    
    Args:
        provider_class: Provider class to register
    """
    get_registry().register_provider(provider_class)