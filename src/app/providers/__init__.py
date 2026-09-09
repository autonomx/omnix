"""
Plugin-based Provider System for LLM providers.

This package contains provider implementations that conform to the BaseProvider interface.
Each provider is a self-contained module that can be dynamically loaded by the registry.
"""

from .base import (
    AuthenticationError,
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ConnectionError,
    ModelInfo,
    ModelNotFoundError,
    ProviderCapability,
    ProviderConfig,
    ProviderError,
)
from .cerebras_provider import CerebrasProvider
from .chatgpt_codex_provider import ChatGPTCodexProvider
from .llamacpp_provider import LlamaCppProvider
from .lmstudio_provider import LMStudioProvider
from .openrouter_provider import OpenRouterProvider
from .registry import ProviderRegistry, get_registry, list_available_providers
from .codex_reliability import install_codex_reliability

# Apply protocol-compatible Codex hardening once at provider-package import time.
install_codex_reliability()

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
    'ChatGPTCodexProvider',
    'LlamaCppProvider'
]