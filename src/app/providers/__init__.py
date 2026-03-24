"""
Plugin-based Provider System for LLM providers.

This package contains provider implementations that conform to the BaseProvider interface.
Each provider is a self-contained module that can be dynamically loaded by the registry.
"""

from .registry import ProviderRegistry, get_registry, list_available_providers
from .base import (
    BaseProvider,
    ProviderConfig,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderCapability,
    ProviderError,
    AuthenticationError,
    ConnectionError,
    ModelNotFoundError
)
from .lmstudio_provider import LMStudioProvider
from .openrouter_provider import OpenRouterProvider
from .cerebras_provider import CerebrasProvider
from .llamacpp_provider import LlamaCppProvider

__all__ = [
    'ProviderRegistry',
    'get_registry',
    'list_available_providers',
    'BaseProvider',
    'ProviderConfig',
    'ChatMessage',
    'ChatResponse',
    'ModelInfo',
    'ProviderCapability',
    'ProviderError',
    'AuthenticationError',
    'ConnectionError',
    'ModelNotFoundError',
    'LMStudioProvider',
    'OpenRouterProvider',
    'CerebrasProvider',
    'LlamaCppProvider'
]