"""Production provider adapter for structured Campaign World Forge topics."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping

from app.providers.base import BaseProvider, ChatMessage, ChatResponse
from app.providers.registry import get_provider

from .world_forge_contract import CampaignTopicNode
from .world_forge_default import ReferenceSafeWorldForgeGenerator
from .world_forge_generation import GeneratedTopic, WorldForgeTopicGenerator


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_COLLECTIONS = (
    "documents",
    "entities",
    "facts",
    "relationships",
    "knowledge_rules",
    "story_threads",
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

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "WorldForgeProviderConfig":
        env = environ or os.environ
        return cls(
            mode=str(env.get("OMNIX_RPG_WORLD_FORGE_MODE") or "auto")
            .strip()
            .casefold(),
            provider=str(
                env.get("OMNIX_RPG_WORLD_FORGE_PROVIDER")
                or env.get("OMNIX_RPG_NARRATIVE_PROVIDER")
                or env.get("OMNIX_LLM_PROVIDER")
                or ""
            ).strip(),
            model=str(
                env.get("OMNIX_RPG_WORLD_FORGE_MODEL")
                or env.get("OMNIX_RPG_NARRATIVE_MODEL")
                or ""
            ).strip(),
            api_key=(
                str(
                    env.get("OMNIX_RPG_WORLD_FORGE_API_KEY")
                    or env.get("OMNIX_RPG_NARRATIVE_API_KEY")
                    or ""
                ).strip()
                or None
            ),
            base_url=(
                str(
                    env.get("OMNIX_RPG_WORLD_FORGE_BASE_URL")
                    or env.get("OMNIX_RPG_NARRATIVE_BASE_URL")
                    or ""
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


def _system_prompt() -> str:
    return (
        "You are the Omnix Campaign World Forge. Return strict JSON only for the "
        "single requested topic. Build rich, internally consistent campaign canon, "
        "not player-facing turn narration. Respect dependency entities and IDs. "
        "Return topic_id plus arrays named documents, entities, facts, relationships, "
        "knowledge_rules, and story_threads, and a provenance object. NPC dossiers "
        "must include appearance, personality, backstory, goals, motives, speech_style, "
        "faction_ids, location_id, secrets, and known_facts. Location dossiers must "
        "include a sensory_profile and region_id. Every factual row must use stable IDs, "
        "generated_proposal authority, approved objective_canon authority, visibility, "
        "and entity_refs. Never invent an unresolved dependency ID."
    )


def _payload(
    node: CampaignTopicNode,
    *,
    seed: int,
    campaign_context: Mapping[str, Any],
    dependency_topics: Mapping[str, GeneratedTopic],
) -> dict[str, Any]:
    return {
        "contract_version": "rpg_world_forge_topic_request_v1",
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
            ChatMessage(role="system", content=_system_prompt()),
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
        for attempt in range(1, self.config.max_retries + 2):
            try:
                response = self.provider.chat_completion(
                    messages,
                    model=self.config.model or None,
                    stream=False,
                    temperature=self.config.temperature,
                    response_format={"type": "json_object"},
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
                    relationships=_rows(
                        raw.get("relationships"), "relationships"
                    ),
                    knowledge_rules=_rows(
                        raw.get("knowledge_rules"), "knowledge_rules"
                    ),
                    story_threads=_rows(
                        raw.get("story_threads"), "story_threads"
                    ),
                    provenance={
                        **dict(raw.get("provenance") or {}),
                        "generator": "structured_world_forge_provider_v1",
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "attempt_count": attempt,
                        "latency_ms": round(
                            (perf_counter() - started) * 1000.0,
                            3,
                        ),
                        "usage": dict(response.usage or {}),
                        "finish_reason": response.finish_reason or "",
                    },
                )
            except Exception as exc:
                last_error = exc
        raise RuntimeError(
            f"structured World Forge provider failed for {node.topic_id} "
            f"after {self.config.max_retries + 1} attempts"
        ) from last_error


class UnavailableWorldForgeTopicGenerator:
    """Fail launch-required generation instead of silently publishing placeholder canon."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, node: CampaignTopicNode, **kwargs: Any) -> GeneratedTopic:
        raise RuntimeError(f"{self.reason}: {node.topic_id}")


def build_production_world_forge_generator(
    config: WorldForgeProviderConfig | None = None,
    *,
    provider_factory: Callable[
        [str, Mapping[str, Any] | None], BaseProvider | None
    ] = get_provider,
) -> WorldForgeTopicGenerator:
    """Resolve the one production World Forge generator for every topic job."""

    resolved = config or WorldForgeProviderConfig.from_environment()
    if not resolved.live_enabled:
        return ReferenceSafeWorldForgeGenerator()
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
        return UnavailableWorldForgeTopicGenerator(
            f"configured World Forge provider could not initialize: {exc}"
        )
    if provider is None:
        return UnavailableWorldForgeTopicGenerator(
            f"configured World Forge provider is unavailable: {resolved.provider}"
        )
    return ReferenceSafeWorldForgeGenerator(
        ProviderWorldForgeTopicGenerator(provider, resolved)
    )
