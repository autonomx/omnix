"""Ports used to compose the live-voice conversation pipeline."""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Protocol


class TranscriptStore(Protocol):
    def get_session(self, session_id: str) -> Any | None: ...
    def append_user_message(self, *args: Any, **kwargs: Any) -> Any: ...
    def append_assistant_message(self, *args: Any, **kwargs: Any) -> Any: ...


class PromptBuilder(Protocol):
    def build(self, *args: Any, **kwargs: Any) -> Sequence[Any]: ...


class LLMStream(Protocol):
    def stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]: ...


class TTSProvider(Protocol):
    provider_name: str

    def generate_audio_stream(
        self,
        *,
        text: str,
        speaker: str | None,
        language: str,
        **kwargs: Any,
    ) -> Iterator[tuple[Any, int, Any]]: ...


class TTSProviderResolver(Protocol):
    def get(self, provider_name: str | None = None) -> TTSProvider | None: ...


class TTSLane(Protocol):
    def stream(
        self,
        provider: TTSProvider,
        *,
        text: str,
        speaker: str | None,
        language: str,
        kwargs: dict[str, Any],
        priority: Any,
        **options: Any,
    ) -> Iterator[tuple[Any, int, Any]]: ...


class SpeculationCache(Protocol):
    def clear(self) -> None: ...
    def snapshot(self) -> Sequence[dict[str, Any]]: ...


class Metrics(Protocol):
    def emit(self, event: str, **details: Any) -> None: ...
