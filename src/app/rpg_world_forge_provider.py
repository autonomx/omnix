"""Production provider adapter for structured Campaign World Forge topics."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, replace
from threading import Lock
from time import perf_counter, sleep
from typing import Any, Callable, Mapping

from app.providers.base import BaseProvider, ChatMessage, ChatResponse
from app.providers.registry import get_provider
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_default import (
    ReferenceSafeWorldForgeGenerator,
)
from app.rpg.session.genesis.world_forge_dossiers import dossier_prompt_contract
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
)


_LOGGER = logging.getLogger(__name__)
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_COLLECTIONS = (
    "documents",
    "entities",
    "facts",
    "relationships",
    "knowledge_rules",
    "story_threads",
)

_WORLD_FORGE_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "topic_id": {"type": "string"},
        **{
            name: {
                "type": "array",
                "items": {"type": "object"},
            }
            for name in _COLLECTIONS
        },
        "provenance": {"type": "object"},
    },
    "required": ["topic_id", *_COLLECTIONS, "provenance"],
}


def _response_formats(provider: str) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Return response modes from strongest constraint to widest compatibility."""

    if str(provider or "").strip().casefold() == "lmstudio":
        return (
            (
                "json_schema",
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "rpg_world_forge_topic",
                        "strict": False,
                        "schema": _WORLD_FORGE_RESPONSE_SCHEMA,
                    },
                },
            ),
            # LM Studio rejects OpenAI's json_object mode.  Text remains valid
            # and the application still requires a JSON object from the model.
            ("text", {"type": "text"}),
        )
    return (
        ("json_object", {"type": "json_object"}),
        ("text", {"type": "text"}),
    )


def _response_format_error(error: Exception) -> bool:
    text = str(error).casefold()
    return any(
        marker in text
        for marker in (
            "response_format",
            "json_schema",
            "json_object",
            "structured output",
        )
    )


def _response_format(provider: str, *, schema_enabled: bool = True) -> dict[str, Any]:
    """Compatibility shim retained for integrations importing this helper."""

    modes = _response_formats(provider)
    if schema_enabled:
        return dict(modes[0][1])
    return dict(modes[-1][1])


@dataclass(frozen=True)
class WorldForgeProviderConfig:
    mode: str = "auto"
    provider: str = ""
    model: str = ""
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: int = 180
    max_retries: int = 2
    temperature: float = 0.6
    max_tokens: int = 8192
    retry_backoff_seconds: float = 1.0
    lmstudio_schema_fallback: bool = True

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "WorldForgeProviderConfig":
        env = environ if environ is not None else os.environ
        return cls(
            mode=str(env.get("OMNIX_RPG_WORLD_FORGE_MODE") or "auto")
            .strip()
            .casefold(),
            provider=str(
                env.get("OMNIX_RPG_WORLD_FORGE_PROVIDER") or ""
            ).strip(),
            model=str(
                env.get("OMNIX_RPG_WORLD_FORGE_MODEL") or ""
            ).strip(),
            api_key=(
                str(
                    env.get("OMNIX_RPG_WORLD_FORGE_API_KEY") or ""
                ).strip()
                or None
            ),
            base_url=(
                str(
                    env.get("OMNIX_RPG_WORLD_FORGE_BASE_URL") or ""
                ).strip()
                or None
            ),
            timeout_seconds=max(
                10,
                min(
                    int(env.get("OMNIX_RPG_WORLD_FORGE_TIMEOUT_SECONDS") or 180),
                    900,
                ),
            ),
            max_retries=max(
                0,
                min(int(env.get("OMNIX_RPG_WORLD_FORGE_MAX_RETRIES") or 2), 5),
            ),
            temperature=max(
                0.0,
                min(
                    float(env.get("OMNIX_RPG_WORLD_FORGE_TEMPERATURE") or 0.6),
                    2.0,
                ),
            ),
            max_tokens=max(
                1024,
                min(int(env.get("OMNIX_RPG_WORLD_FORGE_MAX_TOKENS") or 8192), 32768),
            ),
            retry_backoff_seconds=max(
                0.0,
                min(
                    float(env.get("OMNIX_RPG_WORLD_FORGE_RETRY_BACKOFF_SECONDS") or 1.0),
                    30.0,
                ),
            ),
            lmstudio_schema_fallback=str(
                env.get("OMNIX_RPG_WORLD_FORGE_LMSTUDIO_SCHEMA_FALLBACK") or "true"
            ).strip().casefold() not in {"0", "false", "no", "off"},
        )

    @property
    def live_enabled(self) -> bool:
        return self.mode not in {
            "offline",
            "deterministic",
            "test",
            "disabled",
        } and bool(self.provider)


def _extract_json(content: str) -> Mapping[str, Any]:
    text = _JSON_FENCE.sub("", str(content or "").strip()).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("World Forge provider returned no JSON object")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, Mapping):
        raise ValueError("World Forge provider JSON root must be an object")
    topic = parsed.get("topic")
    return topic if isinstance(topic, Mapping) else parsed


def _system_prompt(node: CampaignTopicNode) -> str:
    return (
        "You are the Omnix Campaign World Forge. Return strict JSON only for the "
        "single requested topic. Build rich, internally consistent campaign canon, "
        "not player-facing turn narration. Respect dependency entities and IDs. "
        "Return topic_id plus arrays named documents, entities, facts, relationships, "
        "knowledge_rules, and story_threads, and a provenance object. Every generated "
        "entity must include short_summary plus a dossier object matching the supplied "
        "rpg_world_entity_dossier_v1 contract. Dossier sections use stable IDs, titled "
        "sections, and one to three substantial paragraphs per substantive section. "
        "Use short_summary only for cards; do not replace the long dossier with a one- "
        "or two-line description. Keep mechanics and canonical references in their "
        "structured fields rather than hiding them in prose. NPC dossiers must include "
        "appearance, personality, backstory, goals, motives, speech_style, faction_ids, "
        "location_id, secrets, and known_facts. Location dossiers must include a "
        "sensory_profile and region_id. Every factual row must use stable IDs, "
        "generated_proposal authority, approved objective_canon authority, visibility, "
        "and entity_refs. Never invent an unresolved dependency ID. The requested "
        f"domain is {node.topic_id}; follow its domain-specific section template exactly."
    )


def _payload(
    node: CampaignTopicNode,
    *,
    seed: int,
    campaign_context: Mapping[str, Any],
    dependency_topics: Mapping[str, GeneratedTopic],
) -> dict[str, Any]:
    return {
        "contract_version": "rpg_world_forge_topic_request_v2",
        "seed": seed,
        "topic": {
            "topic_id": node.topic_id,
            "title": node.title,
            "category": node.category,
            "visibility": node.visibility,
            "target_count": node.target_count,
            "generator_role": node.generator_role,
            "metadata": dict(node.metadata),
        },
        "campaign_context": dict(campaign_context),
        "dependencies": {
            topic_id: topic.as_dict()
            for topic_id, topic in sorted(dependency_topics.items())
        },
        "required_output": {
            "topic_id": node.topic_id,
            "collections": list(_COLLECTIONS),
            "entity_dossier": dossier_prompt_contract(node.topic_id),
        },
    }


def _rows(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"World Forge {name} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"World Forge {name}[{index}] must be an object")
        rows.append(dict(row))
    return tuple(rows)


class ProviderWorldForgeTopicGenerator:
    """Generate one structured canon topic through a configured chat provider."""

    def __init__(self, provider: BaseProvider, config: WorldForgeProviderConfig) -> None:
        self.provider = provider
        self.config = config

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        messages = [
            ChatMessage(role="system", content=_system_prompt(node)),
            ChatMessage(
                role="user",
                content=json.dumps(
                    _payload(
                        node,
                        seed=seed,
                        campaign_context=campaign_context,
                        dependency_topics=dependency_topics,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        ]
        started = perf_counter()
        last_error: Exception | None = None
        response_formats = _response_formats(self.config.provider)
        response_format_index = 0
        prompt_chars = sum(len(message.content) for message in messages)
        for attempt in range(1, self.config.max_retries + 2):
            try:
                response = self.provider.chat_completion(
                    messages,
                    model=self.config.model or None,
                    stream=False,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    response_format=response_formats[response_format_index][1],
                )
                if not isinstance(response, ChatResponse):
                    raise ValueError(
                        "World Forge provider returned a streaming or invalid response"
                    )
                raw = _extract_json(response.content)
                topic_id = str(raw.get("topic_id") or "").strip()
                if topic_id != node.topic_id:
                    raise ValueError(
                        f"World Forge provider returned {topic_id or '<missing>'} "
                        f"for {node.topic_id}"
                    )
                return GeneratedTopic(
                    topic_id=topic_id,
                    documents=_rows(raw.get("documents"), "documents"),
                    entities=_rows(raw.get("entities"), "entities"),
                    facts=_rows(raw.get("facts"), "facts"),
                    relationships=_rows(raw.get("relationships"), "relationships"),
                    knowledge_rules=_rows(
                        raw.get("knowledge_rules"), "knowledge_rules"
                    ),
                    story_threads=_rows(raw.get("story_threads"), "story_threads"),
                    provenance={
                        **dict(raw.get("provenance") or {}),
                        "generator": "structured_world_forge_provider_v2",
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "attempt_count": attempt,
                        "latency_ms": round(
                            (perf_counter() - started) * 1000.0,
                            3,
                        ),
                        "usage": dict(response.usage or {}),
                        "finish_reason": response.finish_reason or "",
                        "entity_dossier_schema": "rpg_world_entity_dossier_v1",
                        "response_format": response_formats[response_format_index][0],
                        "max_tokens": self.config.max_tokens,
                    },
                )
            except Exception as exc:
                last_error = exc
                _LOGGER.warning(
                    "World Forge provider attempt failed provider=%s model=%s topic=%s "
                    "attempt=%s/%s prompt_chars=%s response_format=%s error=%s: %s",
                    self.config.provider,
                    self.config.model,
                    node.topic_id,
                    attempt,
                    self.config.max_retries + 1,
                    prompt_chars,
                    response_formats[response_format_index][0],
                    type(exc).__name__,
                    exc,
                )
                if (
                    self.config.lmstudio_schema_fallback
                    and _response_format_error(exc)
                    and response_format_index + 1 < len(response_formats)
                ):
                    response_format_index += 1
                if attempt <= self.config.max_retries and self.config.retry_backoff_seconds > 0:
                    sleep(self.config.retry_backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(
            f"structured World Forge provider failed for {node.topic_id} "
            f"after {self.config.max_retries + 1} attempts: "
            f"{type(last_error).__name__}: {last_error}"
        ) from last_error


class UnavailableWorldForgeTopicGenerator:
    """Fail launch-required generation instead of publishing placeholder canon."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, node: CampaignTopicNode, **kwargs: Any) -> GeneratedTopic:
        raise RuntimeError(f"{self.reason}: {node.topic_id}")


class FallbackWorldForgeTopicGenerator:
    """Stick to the first healthy generator after a provider failure."""

    def __init__(self, generators: tuple[WorldForgeTopicGenerator, ...]) -> None:
        if not generators:
            raise ValueError("at least one World Forge generator is required")
        self.generators = generators
        self._active_index = 0
        self._lock = Lock()

    def generate(
        self,
        node: CampaignTopicNode,
        **kwargs: Any,
    ) -> GeneratedTopic:
        with self._lock:
            start_index = self._active_index
        last_error: Exception | None = None
        for index in range(start_index, len(self.generators)):
            try:
                topic = self.generators[index].generate(node, **kwargs)
                with self._lock:
                    self._active_index = max(self._active_index, index)
                return topic
            except Exception as exc:
                last_error = exc
                with self._lock:
                    self._active_index = max(self._active_index, index + 1)
        assert last_error is not None
        raise last_error


def build_production_world_forge_generator(
    config: WorldForgeProviderConfig | None = None,
    *,
    provider_factory: Callable[
        [str, Mapping[str, Any] | None], BaseProvider | None
    ] | None = None,
) -> WorldForgeTopicGenerator:
    """Resolve the one production World Forge generator for every topic job."""

    resolved = config or WorldForgeProviderConfig.from_environment()
    settings_routed = config is None or resolved.mode == "auto"
    fallback_behavior = "fail"
    if settings_routed and resolved.mode not in {
        "offline",
        "deterministic",
        "test",
        "disabled",
    }:
        try:
            from app.platform.effective_defaults import (
                effective_llm_route,
                load_effective_profile,
            )

            profile = load_effective_profile()
            provider_id, model_id = effective_llm_route(
                profile,
                "rpg",
                "rpg.world_forge.generate",
            )
            global_settings = getattr(profile, "global_settings", None)
            routing = getattr(global_settings, "routing", None)
            fallback_behavior = str(
                getattr(routing, "fallback_behavior", "fail") or "fail"
            ).strip().casefold()
            provider_key = str(provider_id or "").strip()
            if provider_key.startswith("llm:"):
                provider_key = provider_key.split(":", 1)[1]
            model_key = str(model_id or "").strip()
            model_parts = model_key.split(":", 2)
            if len(model_parts) == 3 and model_parts[0] == "llm":
                model_key = model_parts[2]
            resolved = replace(
                resolved,
                provider=provider_key,
                model=model_key,
            )
        except Exception:
            # Settings may be unavailable during isolated tools and migrations.
            # In that case the existing offline/reference-safe behavior remains.
            pass
    if not resolved.live_enabled:
        return ReferenceSafeWorldForgeGenerator()
    provider_ids = [resolved.provider]
    if (
        settings_routed
        and fallback_behavior == "next-available"
        and resolved.provider != "lmstudio"
    ):
        provider_ids.append("lmstudio")

    generators: list[WorldForgeTopicGenerator] = []
    initialization_errors: list[str] = []
    for provider_id in provider_ids:
        candidate = replace(
            resolved,
            provider=provider_id,
            model=resolved.model if provider_id == resolved.provider else "",
        )
        try:
            if provider_factory is not None:
                provider = provider_factory(
                    provider_id,
                    {
                        "api_key": candidate.api_key,
                        "base_url": candidate.base_url,
                        "model": candidate.model or None,
                        "timeout": candidate.timeout_seconds,
                        "max_retries": candidate.max_retries,
                    },
                )
            elif settings_routed:
                # Settings owns provider URLs and protected keys. Reuse its cache.
                from app import shared

                provider = shared.get_provider(provider_id)
            else:
                provider = get_provider(
                    provider_id,
                    {
                        "api_key": candidate.api_key,
                        "base_url": candidate.base_url,
                        "model": candidate.model or None,
                        "timeout": candidate.timeout_seconds,
                        "max_retries": candidate.max_retries,
                    },
                )
        except Exception as exc:
            initialization_errors.append(f"{provider_id}: {exc}")
            continue
        if provider is None:
            initialization_errors.append(f"{provider_id}: unavailable")
            continue
        generators.append(ProviderWorldForgeTopicGenerator(provider, candidate))

    if not generators:
        return UnavailableWorldForgeTopicGenerator(
            "configured World Forge providers could not initialize: "
            + "; ".join(initialization_errors)
        )
    generator: WorldForgeTopicGenerator = generators[0]
    if len(generators) > 1:
        generator = FallbackWorldForgeTopicGenerator(tuple(generators))
    return ReferenceSafeWorldForgeGenerator(generator)
