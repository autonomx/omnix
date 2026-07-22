"""Production provider adapter for typed Campaign World Forge topics."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, replace
from threading import Lock
from time import perf_counter
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.providers.base import BaseProvider, ChatMessage
from app.providers.registry import get_provider
from app.providers.structured import (
    StructuredCapabilities,
    StructuredContract,
    StructuredOutputGateway,
    StructuredRetryBudget,
)
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_dossiers import dossier_prompt_contract
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
)

_LOGGER = logging.getLogger(__name__)
_COLLECTIONS = (
    "documents",
    "entities",
    "facts",
    "relationships",
    "knowledge_rules",
    "story_threads",
)


class _WorldForgeRow(BaseModel):
    """Typed object envelope for heterogeneous topic rows."""

    model_config = ConfigDict(extra="allow")


class WorldForgeDocument(_WorldForgeRow):
    pass


class WorldForgeEntity(_WorldForgeRow):
    pass


class WorldForgeFact(_WorldForgeRow):
    pass


class WorldForgeRelationship(_WorldForgeRow):
    pass


class WorldForgeKnowledgeRule(_WorldForgeRow):
    pass


class WorldForgeStoryThread(_WorldForgeRow):
    pass


class WorldForgeTopicResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str = Field(min_length=1)
    documents: list[WorldForgeDocument]
    entities: list[WorldForgeEntity]
    facts: list[WorldForgeFact]
    relationships: list[WorldForgeRelationship]
    knowledge_rules: list[WorldForgeKnowledgeRule]
    story_threads: list[WorldForgeStoryThread]
    provenance: dict[str, Any]


def _topic_contract(expected_topic_id: str) -> StructuredContract[WorldForgeTopicResponse]:
    def validate_topic(value: WorldForgeTopicResponse) -> None:
        if value.topic_id != expected_topic_id:
            raise ValueError(
                f"World Forge provider returned {value.topic_id or '<missing>'} "
                f"for {expected_topic_id}"
            )

    return StructuredContract(
        contract_id="rpg.world_forge.topic",
        version=3,
        output_model=WorldForgeTopicResponse,
        semantic_validator=validate_topic,
        schema_profile="canon_strict",
        schema_name="rpg_world_forge_topic",
    )


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
            provider=str(env.get("OMNIX_RPG_WORLD_FORGE_PROVIDER") or "").strip(),
            model=str(env.get("OMNIX_RPG_WORLD_FORGE_MODEL") or "").strip(),
            api_key=(
                str(env.get("OMNIX_RPG_WORLD_FORGE_API_KEY") or "").strip() or None
            ),
            base_url=(
                str(env.get("OMNIX_RPG_WORLD_FORGE_BASE_URL") or "").strip() or None
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
                    float(
                        env.get("OMNIX_RPG_WORLD_FORGE_RETRY_BACKOFF_SECONDS") or 1.0
                    ),
                    30.0,
                ),
            ),
            lmstudio_schema_fallback=str(
                env.get("OMNIX_RPG_WORLD_FORGE_LMSTUDIO_SCHEMA_FALLBACK") or "true"
            ).strip().casefold()
            not in {"0", "false", "no", "off"},
        )

    @property
    def live_enabled(self) -> bool:
        return self.mode not in {
            "offline",
            "deterministic",
            "test",
            "disabled",
        } and bool(self.provider)


class _ConfiguredProviderView:
    """Expose immutable route identity without mutating a shared provider instance."""

    def __init__(self, provider: BaseProvider, provider_name: str) -> None:
        self._provider = provider
        self.provider_name = provider_name or str(
            getattr(provider, "provider_name", provider.__class__.__name__)
        )
        self.config = getattr(provider, "config", None)

    def chat_completion(self, *args: Any, **kwargs: Any) -> Any:
        return self._provider.chat_completion(*args, **kwargs)

    def get_structured_capabilities(self, *args: Any, **kwargs: Any):
        method = getattr(self._provider, "get_structured_capabilities", None)
        if callable(method):
            return method(*args, **kwargs)
        return StructuredCapabilities.default_for_provider(self.provider_name)


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
        "contract_version": "rpg_world_forge_topic_request_v3",
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


def _model_rows(rows: list[_WorldForgeRow]) -> tuple[Mapping[str, Any], ...]:
    return tuple(row.model_dump(mode="python") for row in rows)


class ProviderWorldForgeTopicGenerator:
    """Generate one validated canon topic through a request-local gateway."""

    def __init__(self, provider: BaseProvider, config: WorldForgeProviderConfig) -> None:
        self.transport_provider = provider
        self.provider = _ConfiguredProviderView(provider, config.provider)
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
        total_calls = max(1, self.config.max_retries + 2)
        gateway = StructuredOutputGateway(self.provider)
        outcome = gateway.try_generate(
            messages,
            contract=replace(
                _topic_contract(node.topic_id),
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            ),
            model=self.config.model or None,
            retry_budget=StructuredRetryBudget(
                max_provider_calls=total_calls,
                max_transport_retries=self.config.max_retries,
                max_format_downgrades=(
                    1 if self.config.lmstudio_schema_fallback else 0
                ),
                max_validation_regenerations=self.config.max_retries,
                deadline_seconds=float(self.config.timeout_seconds),
            ),
        )
        diagnostics = outcome.diagnostics
        if outcome.error is not None:
            raise RuntimeError(
                f"structured World Forge provider failed for {node.topic_id} "
                f"after {diagnostics.provider_calls or total_calls} attempts: "
                f"{type(outcome.error).__name__}: {outcome.error}"
            ) from outcome.error
        assert outcome.value is not None
        value = outcome.value
        trusted = diagnostics.as_dict()
        return GeneratedTopic(
            topic_id=value.topic_id,
            documents=_model_rows(value.documents),
            entities=_model_rows(value.entities),
            facts=_model_rows(value.facts),
            relationships=_model_rows(value.relationships),
            knowledge_rules=_model_rows(value.knowledge_rules),
            story_threads=_model_rows(value.story_threads),
            provenance={
                **dict(value.provenance),
                "generator": "structured_world_forge_provider_v1",
                "provider_contract": "rpg_world_forge_topic_request_v3",
                "provider": self.config.provider,
                "model": self.config.model,
                "attempt_count": int(trusted.get("provider_calls") or 1),
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
                "usage": dict(trusted.get("usage") or {}),
                "finish_reason": str(trusted.get("finish_reason") or ""),
                "entity_dossier_schema": "rpg_world_entity_dossier_v1",
                "response_format": str(trusted.get("selected_mode") or ""),
                "structured_contract": "rpg.world_forge.topic.v3",
                "schema_hash": str(trusted.get("schema_hash") or ""),
                "max_tokens": self.config.max_tokens,
            },
        )


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
    ]
    | None = None,
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
