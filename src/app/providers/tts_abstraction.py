"""
Simplified TTS Provider Abstraction Layer.

Provides a clean interface for swapping TTS providers without touching core logic.
Built on top of the existing BaseTTSProvider/AudioProviderRegistry system.
"""

import base64
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    """Abstract base class for simplified TTS providers.

    Provides a minimal interface for TTS generation.
    """

    @abstractmethod
    def generate(self, text: str, speaker: Optional[str] = None, **kwargs) -> bytes:
        """Generate audio from text. Returns raw audio bytes."""
        pass

    @abstractmethod
    def stream(self, text: str, speaker: Optional[str] = None, **kwargs) -> Iterator[bytes]:
        """Stream audio generation. Yields audio chunks."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass


class OpenAITTSProvider(TTSProvider):
    """TTS provider using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "tts-1",
        voice: str = "alloy",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voice = voice

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, text: str, speaker: Optional[str] = None, **kwargs) -> bytes:
        """Call OpenAI TTS API and return audio bytes."""
        voice = speaker or self._voice
        model = kwargs.get("model", self._model)
        payload: Dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice,
        }
        response_format = kwargs.get("response_format")
        if response_format:
            payload["response_format"] = response_format

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            resp = requests.post(
                f"{self._base_url}/audio/speech",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            logger.error("OpenAI TTS request failed: %s", exc)
            return b""

    def stream(self, text: str, speaker: Optional[str] = None, **kwargs) -> Iterator[bytes]:
        """Stream from OpenAI TTS API."""
        voice = speaker or self._voice
        model = kwargs.get("model", self._model)
        payload: Dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice,
        }
        response_format = kwargs.get("response_format")
        if response_format:
            payload["response_format"] = response_format

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            resp = requests.post(
                f"{self._base_url}/audio/speech",
                json=payload,
                headers=headers,
                timeout=30,
                stream=True,
            )
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        except requests.RequestException as exc:
            logger.error("OpenAI TTS streaming request failed: %s", exc)


class LocalModelTTSProvider(TTSProvider):
    """TTS provider wrapping a local TTS model server (like the existing system)."""

    def __init__(self, base_url: str = "http://localhost:8020"):
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "local"

    def generate(self, text: str, speaker: Optional[str] = None, **kwargs) -> bytes:
        """Call local TTS server and return audio bytes."""
        payload: Dict[str, Any] = {"text": text}
        if speaker:
            payload["speaker"] = speaker
        payload.update(kwargs)

        try:
            resp = requests.post(
                f"{self._base_url}/api/tts",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            audio_b64 = data.get("audio", "")
            if audio_b64:
                return base64.b64decode(audio_b64)
            return b""
        except requests.RequestException as exc:
            logger.error("Local TTS request failed: %s", exc)
            return b""
        except (ValueError, KeyError) as exc:
            logger.error("Failed to decode local TTS response: %s", exc)
            return b""

    def stream(self, text: str, speaker: Optional[str] = None, **kwargs) -> Iterator[bytes]:
        """Stream from local TTS server."""
        payload: Dict[str, Any] = {"text": text}
        if speaker:
            payload["speaker"] = speaker
        payload.update(kwargs)

        try:
            resp = requests.post(
                f"{self._base_url}/api/tts/stream",
                json=payload,
                timeout=120,
                stream=True,
            )
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        except requests.RequestException as exc:
            logger.error("Local TTS streaming request failed: %s", exc)


# ---------------------------------------------------------------------------
# Registry for simplified providers
# ---------------------------------------------------------------------------

_tts_providers: Dict[str, TTSProvider] = {}


def register_provider(name: str, provider: TTSProvider) -> None:
    """Register a TTS provider by name."""
    _tts_providers[name] = provider


def get_provider(name: str) -> Optional[TTSProvider]:
    """Get a registered TTS provider by name."""
    return _tts_providers.get(name)


def list_providers() -> List[str]:
    """List all registered provider names."""
    return list(_tts_providers.keys())


def unregister_provider(name: str) -> bool:
    """Remove a provider from registry."""
    if name in _tts_providers:
        del _tts_providers[name]
        return True
    return False
