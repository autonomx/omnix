"""Small deterministic provider fakes shared by characterization scenarios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any


def _message_payload(message: Any) -> dict[str, Any]:
    if isinstance(message, Mapping):
        return {str(key): value for key, value in message.items()}
    to_dict = getattr(message, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {
        "role": str(getattr(message, "role", "")),
        "content": str(getattr(message, "content", "")),
    }


def prompt_digest(messages: Sequence[Any]) -> str:
    """Hash a canonical provider prompt for response lookup and audit evidence."""

    canonical = json.dumps(
        [_message_payload(message) for message in messages],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FakeChatChunk:
    content: str
    model: str
    usage: dict[str, int]


class FakeLLMProvider:
    """Script streamed output by the SHA-256 hash of its canonical prompt."""

    def __init__(
        self,
        responses_by_prompt_hash: Mapping[str, str | Sequence[str]],
        *,
        model_id: str = "fixture-model",
    ) -> None:
        self.responses_by_prompt_hash = dict(responses_by_prompt_hash)
        self.model_id = model_id
        self.calls: list[dict[str, Any]] = []

    def chat_completion(
        self,
        *,
        messages: Sequence[Any],
        model: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> FakeChatChunk | Any:
        prompt = [_message_payload(message) for message in messages]
        digest = prompt_digest(prompt)
        self.calls.append(
            {
                "prompt_hash": digest,
                "messages": prompt,
                "model": model or self.model_id,
                "stream": stream,
                "kwargs": kwargs,
            }
        )
        if digest not in self.responses_by_prompt_hash:
            raise AssertionError(
                f"no FakeLLMProvider script for prompt hash {digest}: "
                f"{json.dumps(prompt, ensure_ascii=False, sort_keys=True)}"
            )
        scripted = self.responses_by_prompt_hash[digest]
        chunks = [scripted] if isinstance(scripted, str) else list(scripted)
        values = [
            FakeChatChunk(content=chunk, model=model or self.model_id, usage={"completion_tokens": 7})
            for chunk in chunks
        ]
        if stream:
            return iter(values)
        return FakeChatChunk(
            content="".join(chunks),
            model=model or self.model_id,
            usage={"completion_tokens": 7},
        )


class FakeTTS:
    """Return repeatable frame bytes for a text phrase without loading a model."""

    def __init__(self, *, frame_count: int = 3, frame_bytes: int = 8) -> None:
        if frame_count < 0 or frame_bytes < 1:
            raise ValueError("FakeTTS frame dimensions must be non-negative and non-zero")
        self.frame_count = frame_count
        self.frame_bytes = frame_bytes

    def synthesize(self, text: str) -> tuple[bytes, ...]:
        seed = text.encode("utf-8")
        return tuple(
            hashlib.sha256(seed + index.to_bytes(4, "big")).digest()[: self.frame_bytes]
            for index in range(self.frame_count)
        )


class FakeMarketData:
    """Fixed, provider-free bar series keyed by symbol and optional timeframe."""

    def __init__(self, bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        self._bars = {
            symbol: tuple(dict(bar) for bar in bars)
            for symbol, bars in bars_by_symbol.items()
        }
        self.calls: list[dict[str, Any]] = []

    def bars(
        self,
        symbol: str,
        *,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> tuple[dict[str, Any], ...]:
        self.calls.append({"symbol": symbol, "timeframe": timeframe, "limit": limit})
        if symbol not in self._bars:
            raise KeyError(f"no fixed market bars for {symbol}")
        values = self._bars[symbol]
        if limit is not None:
            values = () if limit <= 0 else values[-limit:]
        return tuple(dict(bar) for bar in values)
