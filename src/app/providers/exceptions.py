"""
Custom exceptions for the provider plugin system.
"""

from .base import ProviderError


class ProviderRegistrationError(ProviderError):
    """Error during provider registration or discovery."""
    pass


class ProviderConfigurationError(ProviderError):
    """Error in provider configuration."""
    pass


class ProviderNotAvailableError(ProviderError):
    """Provider is not available or not installed."""
    pass


class TtsEngineNotLoaded(ProviderError):
    """A job pinned to one TTS engine found another one loaded; nothing was switched."""

    def __init__(self, requested: str, loaded: str = "") -> None:
        self.requested = requested
        self.loaded = loaded
        loaded_note = f" (the loaded engine is {loaded})" if loaded else ""
        super().__init__(
            f"TTS engine {requested} is not loaded{loaded_note}; select it in Voice Studio and try again"
        )


class StreamInterruptedError(ProviderError):
    """Stream was interrupted or cancelled."""
    pass


class RateLimitError(ProviderError):
    """Rate limit exceeded."""
    pass


class InsufficientQuotaError(ProviderError):
    """Insufficient quota or credits."""
    pass