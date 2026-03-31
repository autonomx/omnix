"""
Audio Provider Registry - Factory for Audio Providers

This module implements a registry that automatically discovers audio provider plugins
and provides a factory for creating TTS and STT provider instances.
"""

import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from .audio_base import AudioProviderConfig, BaseSTTProvider, BaseTTSProvider
from .exceptions import ProviderRegistrationError


class AudioProviderRegistry:
    """
    Registry for audio provider plugins.
    
    Handles automatic discovery of TTS and STT provider classes,
    registration, and factory-based instantiation.
    """
    
    def __init__(self):
        """Initialize the audio provider registry."""
        self._tts_providers: Dict[str, Type[BaseTTSProvider]] = {}
        self._stt_providers: Dict[str, Type[BaseSTTProvider]] = {}
        self._discovered = False
        
    def discover_providers(self) -> None:
        """
        Auto-discover audio provider classes from the providers package.
        
        Scans all .py files in the providers directory and registers any classes
        that inherit from BaseTTSProvider or BaseSTTProvider.
        """
        if self._discovered:
            return
            
        providers_dir = Path(__file__).parent
        self._tts_providers = {}
        self._stt_providers = {}
        
        # Import all Python modules in the providers package
        for module_file in providers_dir.glob("*.py"):
            module_name = module_file.stem
            
            # Skip these files
            if module_name in ["__init__", "base", "registry", "exceptions", "audio_base"]:
                continue
                
            try:
                # Import the module
                full_module_name = f"app.providers.{module_name}"
                module = importlib.import_module(full_module_name)
                
                # Find all TTS provider classes
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseTTSProvider) and 
                        obj != BaseTTSProvider and 
                        obj.__module__ == full_module_name):
                        
                        # Get the provider name by calling the property
                        try:
                            provider_name = obj.provider_name.fget(None)
                        except:
                            # If it's a property, try to get it differently
                            provider_name = getattr(obj, 'provider_name', None)
                            if hasattr(provider_name, 'fget'):
                                try:
                                    provider_name = provider_name.fget(None)
                                except:
                                    continue
                        
                        if provider_name and provider_name != "base":
                            if provider_name in self._tts_providers:
                                print(f"[WARNING] TTS Provider '{provider_name}' already registered, overwriting")
                            self._tts_providers[provider_name] = obj
                            print(f"[INFO] Registered TTS provider: {provider_name}")
                
                # Find all STT provider classes
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseSTTProvider) and 
                        obj != BaseSTTProvider and 
                        obj.__module__ == full_module_name):
                        
                        # Get the provider name by calling the property
                        try:
                            provider_name = obj.provider_name.fget(None)
                        except:
                            # If it's a property, try to get it differently
                            provider_name = getattr(obj, 'provider_name', None)
                            if hasattr(provider_name, 'fget'):
                                try:
                                    provider_name = provider_name.fget(None)
                                except:
                                    continue
                        
                        if provider_name and provider_name != "base":
                            if provider_name in self._stt_providers:
                                print(f"[WARNING] STT Provider '{provider_name}' already registered, overwriting")
                            self._stt_providers[provider_name] = obj
                            print(f"[INFO] Registered STT provider: {provider_name}")
                        
            except Exception as e:
                print(f"Error discovering providers in {module_name}: {e}")
                
        self._discovered = True
        print(f"[INFO] Audio provider discovery complete. {len(self._tts_providers)} TTS and {len(self._stt_providers)} STT providers available")
    
    def register_tts_provider(self, provider_class: Type[BaseTTSProvider]) -> None:
        """
        Manually register a TTS provider class.
        
        Args:
            provider_class: TTS provider class inheriting from BaseTTSProvider
            
        Raises:
            ProviderRegistrationError: If provider name is invalid or already registered
        """
        if not issubclass(provider_class, BaseTTSProvider):
            raise ProviderRegistrationError(f"{provider_class.__name__} must inherit from BaseTTSProvider")
            
        provider_name = provider_class.provider_name
        if not provider_name or provider_name == "base":
            raise ProviderRegistrationError(f"Invalid TTS provider name: {provider_name}")
            
        if provider_name in self._tts_providers:
            raise ProviderRegistrationError(f"TTS Provider '{provider_name}' is already registered")
            
        self._tts_providers[provider_name] = provider_class
        print(f"[INFO] Manually registered TTS provider: {provider_name}")
    
    def register_stt_provider(self, provider_class: Type[BaseSTTProvider]) -> None:
        """
        Manually register an STT provider class.
        
        Args:
            provider_class: STT provider class inheriting from BaseSTTProvider
            
        Raises:
            ProviderRegistrationError: If provider name is invalid or already registered
        """
        if not issubclass(provider_class, BaseSTTProvider):
            raise ProviderRegistrationError(f"{provider_class.__name__} must inherit from BaseSTTProvider")
            
        provider_name = provider_class.provider_name
        if not provider_name or provider_name == "base":
            raise ProviderRegistrationError(f"Invalid STT provider name: {provider_name}")
            
        if provider_name in self._stt_providers:
            raise ProviderRegistrationError(f"STT Provider '{provider_name}' is already registered")
            
        self._stt_providers[provider_name] = provider_class
        print(f"[INFO] Manually registered STT provider: {provider_name}")
    
    def unregister_tts_provider(self, provider_name: str) -> bool:
        """
        Unregister a TTS provider.
        
        Args:
            provider_name: Name of the TTS provider to unregister
            
        Returns:
            True if provider was unregistered, False if not found
        """
        if provider_name in self._tts_providers:
            del self._tts_providers[provider_name]
            print(f"[INFO] Unregistered TTS provider: {provider_name}")
            return True
        return False
    
    def unregister_stt_provider(self, provider_name: str) -> bool:
        """
        Unregister an STT provider.
        
        Args:
            provider_name: Name of the STT provider to unregister
            
        Returns:
            True if provider was unregistered, False if not found
        """
        if provider_name in self._stt_providers:
            del self._stt_providers[provider_name]
            print(f"[INFO] Unregistered STT provider: {provider_name}")
            return True
        return False
    
    def get_tts_provider_class(self, provider_name: str) -> Optional[Type[BaseTTSProvider]]:
        """
        Get the TTS provider class for a given provider name.
        
        Args:
            provider_name: Name of the TTS provider
            
        Returns:
            TTS provider class or None if not found
        """
        if not self._discovered:
            self.discover_providers()
        return self._tts_providers.get(provider_name)
    
    def get_stt_provider_class(self, provider_name: str) -> Optional[Type[BaseSTTProvider]]:
        """
        Get the STT provider class for a given provider name.
        
        Args:
            provider_name: Name of the STT provider
            
        Returns:
            STT provider class or None if not found
        """
        if not self._discovered:
            self.discover_providers()
        return self._stt_providers.get(provider_name)
    
    def list_tts_providers(self) -> List[Dict[str, Any]]:
        """
        Get list of all registered TTS providers with metadata.
        
        Returns:
            List of dictionaries with TTS provider information
        """
        if not self._discovered:
            self.discover_providers()
            
        providers_list = []
        for name, provider_class in self._tts_providers.items():
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
                print(f"Error getting info for TTS provider {name}: {e}")
                
        return providers_list
    
    def list_stt_providers(self) -> List[Dict[str, Any]]:
        """
        Get list of all registered STT providers with metadata.
        
        Returns:
            List of dictionaries with STT provider information
        """
        if not self._discovered:
            self.discover_providers()
            
        providers_list = []
        for name, provider_class in self._stt_providers.items():
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
                print(f"Error getting info for STT provider {name}: {e}")
                
        return providers_list
    
    def create_tts_provider(
        self,
        provider_name: str,
        config: Optional[Dict[str, Any]] = None,
        provider_config: Optional[AudioProviderConfig] = None
    ) -> Optional[BaseTTSProvider]:
        """
        Factory method to create a TTS provider instance.
        
        Args:
            provider_name: Name of the TTS provider to instantiate
            config: Dictionary with configuration (alternative to provider_config)
            provider_config: AudioProviderConfig instance (preferred)
            
        Returns:
            TTS provider instance or None if provider not found
            
        Raises:
            ProviderRegistrationError: If provider class can't be instantiated
        """
        if not self._discovered:
            self.discover_providers()
            
        provider_class = self._tts_providers.get(provider_name)
        if not provider_class:
            print(f"TTS Provider '{provider_name}' not found")
            return None
            
        # Build AudioProviderConfig
        if provider_config:
            final_config = provider_config
        elif config:
            final_config = AudioProviderConfig(
                provider_type=provider_name,
                base_url=config.get("base_url"),
                timeout=config.get("timeout", 300),
                max_retries=config.get("max_retries", 3),
                extra_params=config.get("extra_params", {})
            )
        else:
            # Use empty config, provider should provide defaults
            final_config = AudioProviderConfig(provider_type=provider_name)
            
        try:
            # Create provider instance with config dict
            provider_instance = provider_class(config=final_config.to_dict())
            return provider_instance
        except Exception as e:
            raise ProviderRegistrationError(
                f"Failed to instantiate TTS provider '{provider_name}': {e}"
            ) from e
    
    def create_stt_provider(
        self,
        provider_name: str,
        config: Optional[Dict[str, Any]] = None,
        provider_config: Optional[AudioProviderConfig] = None
    ) -> Optional[BaseSTTProvider]:
        """
        Factory method to create an STT provider instance.
        
        Args:
            provider_name: Name of the STT provider to instantiate
            config: Dictionary with configuration (alternative to provider_config)
            provider_config: AudioProviderConfig instance (preferred)
            
        Returns:
            STT provider instance or None if provider not found
            
        Raises:
            ProviderRegistrationError: If provider class can't be instantiated
        """
        if not self._discovered:
            self.discover_providers()
            
        provider_class = self._stt_providers.get(provider_name)
        if not provider_class:
            print(f"STT Provider '{provider_name}' not found")
            return None
            
        # Build AudioProviderConfig
        if provider_config:
            final_config = provider_config
        elif config:
            final_config = AudioProviderConfig(
                provider_type=provider_name,
                base_url=config.get("base_url"),
                timeout=config.get("timeout", 300),
                max_retries=config.get("max_retries", 3),
                extra_params=config.get("extra_params", {})
            )
        else:
            # Use empty config, provider should provide defaults
            final_config = AudioProviderConfig(provider_type=provider_name)
            
        try:
            # Create provider instance with config dict
            provider_instance = provider_class(config=final_config.to_dict())
            return provider_instance
        except Exception as e:
            raise ProviderRegistrationError(
                f"Failed to instantiate STT provider '{provider_name}': {e}"
            ) from e
    
    def clear(self) -> None:
        """Clear all registered providers (useful for testing)."""
        self._tts_providers.clear()
        self._stt_providers.clear()
        self._discovered = False



# Global registry instance
_registry = AudioProviderRegistry()


def get_audio_registry() -> AudioProviderRegistry:
    """
    Get the global audio provider registry instance.
    
    Returns:
        AudioProviderRegistry singleton
    """
    return _registry


# Convenience functions
def get_tts_provider(provider_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[BaseTTSProvider]:
    """
    Convenience function to get a TTS provider instance.
    
    Args:
        provider_name: Name of the TTS provider
        config: Optional configuration dictionary
        
    Returns:
        TTS provider instance or None
    """
    return get_audio_registry().create_tts_provider(provider_name, config)


def get_stt_provider(provider_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[BaseSTTProvider]:
    """
    Convenience function to get an STT provider instance.
    
    Args:
        provider_name: Name of the STT provider
        config: Optional configuration dictionary
        
    Returns:
        STT provider instance or None
    """
    return get_audio_registry().create_stt_provider(provider_name, config)


def list_available_tts_providers() -> List[Dict[str, Any]]:
    """
    Get list of all available TTS providers.
    
    Returns:
        List of TTS provider metadata dictionaries
    """
    return get_audio_registry().list_tts_providers()


def list_available_stt_providers() -> List[Dict[str, Any]]:
    """
    Get list of all available STT providers.
    
    Returns:
        List of STT provider metadata dictionaries
    """
    return get_audio_registry().list_stt_providers()


def register_tts_provider(provider_class: Type[BaseTTSProvider]) -> None:
    """
    Register a TTS provider class with the global registry.
    
    Args:
        provider_class: TTS provider class to register
    """
    get_audio_registry().register_tts_provider(provider_class)


def register_stt_provider(provider_class: Type[BaseSTTProvider]) -> None:
    """
    Register an STT provider class with the global registry.
    
    Args:
        provider_class: STT provider class to register
    """
    get_audio_registry().register_stt_provider(provider_class)
