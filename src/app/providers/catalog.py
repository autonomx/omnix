"""The explicit list of provider implementations (WP-7.2 Part A).

Registries load providers from this catalog instead of importing every module
in the package and registering whatever subclasses they find. Adding a
provider means adding its spec here; an id may appear once per kind.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Literal

ProviderKind = Literal["llm", "tts", "stt"]


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    kind: ProviderKind
    module: str
    attribute: str
    capabilities: frozenset[str]

    def load(self) -> type:
        """Import the implementation; its declared id must match the spec."""
        provider_class = getattr(importlib.import_module(self.module), self.attribute)
        declared = getattr(provider_class, "provider_name", None)
        if isinstance(declared, property):
            declared = declared.fget(None)
        if declared != self.id:
            raise ValueError(f"{self.module}.{self.attribute} declares provider id {declared!r}, catalog says {self.id!r}")
        return provider_class


def _llm(id: str, module: str, attribute: str, *capabilities: str) -> ProviderSpec:
    return ProviderSpec(id, "llm", f"app.providers.{module}", attribute, frozenset(("chat", *capabilities)))


CATALOG: tuple[ProviderSpec, ...] = (
    _llm("cerebras", "cerebras_provider", "CerebrasProvider", "streaming", "models"),
    _llm("chatgpt_codex", "chatgpt_codex_provider", "ChatGPTCodexProvider", "streaming", "tools"),
    _llm("llamacpp", "llamacpp_provider", "LlamaCppProvider", "streaming", "models"),
    _llm("lmstudio", "lmstudio_provider", "LMStudioProvider", "streaming", "models", "cancellation"),
    _llm("openai_compatible", "openai_compatible_provider", "OpenAICompatibleProvider", "streaming", "models"),
    _llm("openrouter", "openrouter_provider", "OpenRouterProvider", "streaming", "models"),
    ProviderSpec(
        "faster-qwen3-tts", "tts", "app.providers.faster_qwen3_tts_provider", "FasterQwen3TTSProvider",
        frozenset({"synthesis", "streaming", "voice_clone"}),
    ),
    ProviderSpec("parakeet", "stt", "app.providers.audio_plugins", "ParakeetSTT", frozenset({"transcription"})),
)


def specs(kind: ProviderKind) -> tuple[ProviderSpec, ...]:
    return tuple(spec for spec in CATALOG if spec.kind == kind)


def _check_unique(catalog: tuple[ProviderSpec, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for spec in catalog:
        key = (spec.kind, spec.id)
        if key in seen:
            raise ValueError(f"duplicate {spec.kind} provider id {spec.id!r} in the catalog")
        seen.add(key)


_check_unique(CATALOG)

__all__ = ["CATALOG", "ProviderKind", "ProviderSpec", "specs"]
