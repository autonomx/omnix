"""Production provider adapter for structured RPG narrative generation."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from app.providers.base import BaseProvider, ChatMessage, ChatResponse
from app.providers.registry import get_provider
from app.rpg.narrative_engine import DeterministicNarrativeWriter, NarrativeWriter
from app.rpg.narrative_engine.contracts import EvidenceRecord, TurnPresentationRequest
from app.rpg.narrative_engine.planner import NarrativePlan
from app.rpg.narrative_engine.writer import (
    WriterResult,
    parse_structured_blocks,
    writer_payload,
)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class NarrativeProviderConfig:
    mode: str = "auto"
    provider: str = ""
    model: str = ""
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: int = 90
    max_retries: int = 2
    temperature: float = 0.4

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "NarrativeProviderConfig":
        env = environ or os.environ
        return cls(
            mode=str(env.get("OMNIX_RPG_NARRATIVE_WRITER_MODE") or "auto").strip().casefold(),
            provider=str(
                env.get("OMNIX_RPG_NARRATIVE_PROVIDER")
                or env.get("OMNIX_LLM_PROVIDER")
                or ""
            ).strip(),
            model=str(env.get("OMNIX_RPG_NARRATIVE_MODEL") or "").strip(),
            api_key=(str(env.get("OMNIX_RPG_NARRATIVE_API_KEY") or "").strip() or None),
            base_url=(str(env.get("OMNIX_RPG_NARRATIVE_BASE_URL") or "").strip() or None),
            timeout_seconds=max(
                5,
                min(int(env.get("OMNIX_RPG_NARRATIVE_TIMEOUT_SECONDS") or 90), 600),
            ),
            max_retries=max(
                0,
                min(int(env.get("OMNIX_RPG_NARRATIVE_MAX_RETRIES") or 2), 5),
            ),
            temperature=max(
                0.0,
                min(float(env.get("OMNIX_RPG_NARRATIVE_TEMPERATURE") or 0.4), 2.0),
            ),
        )

    @property
    def live_enabled(self) -> bool:
        return self.mode not in {"offline", "deterministic", "test", "disabled"} and bool(self.provider)


def _extract_json(content: str) -> Mapping[str, Any]:
    text = _JSON_FENCE.sub("", str(content or "").strip()).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("narrative provider returned no JSON object")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, Mapping):
        raise ValueError("narrative provider JSON root must be an object")
    return parsed


def _system_prompt() -> str:
    return (
        "You are the Omnix RPG Narrative Writer. Return strict JSON only. "
        "Follow the ordered beat contracts exactly. Use only each beat's approved evidence. "
        "Return exactly one block per beat and include a claims array for every factual assertion. "
        "Never mutate simulation state, invent secrets, choose for the player, or expose hidden evidence."
    )


class ProviderNarrativeGenerator:
    """Callable bridge from provider chat completion to structured JSON."""

    def __init__(self, provider: BaseProvider, config: NarrativeProviderConfig) -> None:
        self.provider = provider
        self.config = config
        self.last_attempt_count = 0
        self.last_usage: Mapping[str, Any] = {}

    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        messages = [
            ChatMessage(role="system", content=_system_prompt()),
            ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        ]
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 2):
            self.last_attempt_count = attempt
            try:
                response = self.provider.chat_completion(
                    messages,
                    model=self.config.model or None,
                    stream=False,
                    temperature=self.config.temperature,
                    response_format={"type": "json_object"},
                )
                if not isinstance(response, ChatResponse):
                    raise ValueError("narrative provider returned a streaming or invalid response")
                self.last_usage = dict(response.usage or {})
                parsed = dict(_extract_json(response.content))
                metadata = dict(parsed.get("metadata") or {})
                metadata.update(
                    {
                        "provider_attempt_count": attempt,
                        "finish_reason": response.finish_reason or "",
                        "usage": dict(response.usage or {}),
                    }
                )
                parsed["metadata"] = metadata
                return parsed
            except Exception as exc:
                last_error = exc
        raise RuntimeError(
            f"structured RPG narrative provider failed after {self.last_attempt_count} attempts"
        ) from last_error


class ProductionStructuredNarrativeWriter:
    """Provider-backed writer with structured blocks and attempt telemetry."""

    def __init__(self, generator: ProviderNarrativeGenerator) -> None:
        self.generator = generator

    def write(
        self,
        request: TurnPresentationRequest,
        plan: NarrativePlan,
        evidence: Sequence[EvidenceRecord],
    ) -> WriterResult:
        started = perf_counter()
        raw = self.generator(writer_payload(request, plan, evidence))
        blocks = parse_structured_blocks(raw, plan)
        return WriterResult(
            blocks=blocks,
            source="structured_provider",
            provider=self.generator.config.provider,
            model=self.generator.config.model,
            latency_ms=round((perf_counter() - started) * 1000.0, 3),
            attempt_count=max(1, self.generator.last_attempt_count),
            raw_metadata=dict(raw.get("metadata") or {}),
        )


class UnavailableNarrativeWriter:
    """Raise inside validation orchestration so the canonical fallback is recorded."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def write(self, request, plan, evidence) -> WriterResult:
        raise RuntimeError(self.reason)


def build_production_narrative_writer(
    config: NarrativeProviderConfig | None = None,
    *,
    provider_factory: Callable[[str, Mapping[str, Any] | None], BaseProvider | None] = get_provider,
) -> NarrativeWriter:
    """Create the configured live structured writer or an explicit safe fallback."""

    resolved = config or NarrativeProviderConfig.from_environment()
    if not resolved.live_enabled:
        return DeterministicNarrativeWriter()
    try:
        provider = provider_factory(
            resolved.provider,
            {
                "api_key": resolved.api_key,
                "base_url": resolved.base_url,
                "model": resolved.model or None,
                "timeout": resolved.timeout_seconds,
                "max_retries": resolved.max_retries,
            },
        )
    except Exception as exc:
        return UnavailableNarrativeWriter(
            f"configured RPG narrative provider could not initialize: {exc}"
        )
    if provider is None:
        return UnavailableNarrativeWriter(
            f"configured RPG narrative provider is unavailable: {resolved.provider}"
        )
    return ProductionStructuredNarrativeWriter(
        ProviderNarrativeGenerator(provider, resolved)
    )
