"""Production provider adapter for typed Campaign World Forge topics."""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, replace
from threading import BoundedSemaphore, Lock
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
_LMSTUDIO_WORLD_FORGE_CALLS = BoundedSemaphore(2)
_ENTITY_ID_PREFIXES = {
    "areas": "area",
    "classes": "class",
    "encounter_seeds": "encounter",
    "factions": "faction",
    "feats": "feat",
    "items": "item",
    "locations": "location",
    "monsters": "monster",
    "npcs": "npc",
    "one_shots": "one_shot",
    "opening_scenarios": "opening",
    "points_of_interest": "poi",
    "quests": "quest",
    "races": "race",
    "regions": "region",
    "spells": "spell",
}


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


class WorldForgeEntityRegistryItem(BaseModel):
    """A compact, canonical slot that a later dossier call must expand."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    distinction: str = Field(min_length=1)


class WorldForgeEntityRegistryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str = Field(min_length=1)
    entities: list[WorldForgeEntityRegistryItem]
    provenance: dict[str, Any]


def _topic_contract(
    expected_topic_id: str,
    *,
    expected_entity_count: int | None = None,
    expected_entity_ids: tuple[str, ...] = (),
    expected_entity_names: tuple[str, ...] = (),
) -> StructuredContract[WorldForgeTopicResponse]:
    def validate_topic(value: WorldForgeTopicResponse) -> None:
        if value.topic_id != expected_topic_id:
            raise ValueError(
                f"World Forge provider returned {value.topic_id or '<missing>'} "
                f"for {expected_topic_id}"
            )
        if (
            expected_entity_count is not None
            and len(value.entities) != expected_entity_count
        ):
            raise ValueError(
                f"World Forge provider returned {len(value.entities)} entities for "
                f"{expected_topic_id}; expected {expected_entity_count}"
            )
        if expected_entity_ids:
            actual_ids = tuple(
                str(row.get("id") or row.get("entity_id") or "")
                for row in _model_rows(value.entities)
            )
            if set(actual_ids) != set(expected_entity_ids) or len(actual_ids) != len(
                set(actual_ids)
            ):
                raise ValueError(
                    "World Forge provider returned entity IDs "
                    f"{list(actual_ids)} for {expected_topic_id}; expected "
                    f"{list(expected_entity_ids)}"
                )
        if expected_entity_names:
            actual_names = tuple(
                str(row.get("name") or row.get("title") or "").strip()
                for row in _model_rows(value.entities)
            )
            if actual_names != expected_entity_names:
                raise ValueError(
                    "World Forge provider returned entity names "
                    f"{list(actual_names)} for {expected_topic_id}; expected "
                    f"{list(expected_entity_names)}"
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
    entity_batch_size: int = 1
    entity_batch_workers: int = 2
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
            entity_batch_size=max(
                1,
                min(
                    int(
                        env.get("OMNIX_RPG_WORLD_FORGE_ENTITY_BATCH_SIZE") or 1
                    ),
                    8,
                ),
            ),
            entity_batch_workers=max(
                1,
                min(
                    int(
                        env.get("OMNIX_RPG_WORLD_FORGE_ENTITY_BATCH_WORKERS")
                        or 2
                    ),
                    2,
                ),
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


def _system_prompt(
    node: CampaignTopicNode,
    *,
    batch_index: int | None = None,
    batch_count: int | None = None,
    existing_entities: tuple[Mapping[str, str], ...] = (),
    assigned_entity_ids: tuple[str, ...] = (),
    assigned_entities: tuple[Mapping[str, str], ...] = (),
) -> str:
    prompt = (
        "You are the Omnix Campaign World Forge. Return strict JSON only for the "
        "single requested topic. Build rich, internally consistent campaign canon, "
        "not player-facing turn narration. The campaign_context.world_brief is "
        "authoritative: its title and description override generic genre, tone, or "
        "template labels. Ground every name, institution, conflict, technology, "
        "culture, creature, and location in that brief and its dependencies. Do not "
        "fall back to generic fantasy conventions (such as magic, elves, kingdoms, "
        "or medieval classes) unless the world brief explicitly supports them. Produce "
        "exactly the requested target_count of distinct, substantive entities. Never "
        "pad output with numbered topic names or generic placeholder canon. Respect "
        "dependency entities and IDs. "
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
        "and entity_refs. Facts use content for a concise one-sentence canon summary "
        "and expanded_description for one or two self-contained lore paragraphs that "
        "explain origins, impact, or consequences. Never invent an unresolved dependency "
        "ID. The requested "
        f"domain is {node.topic_id}; follow its domain-specific section template exactly."
    )
    if batch_index is None or batch_count is None:
        return prompt
    exclusions = ", ".join(
        f"{row.get('id') or '<unknown>'} ({row.get('name') or 'unnamed'})"
        for row in existing_entities
    )
    assigned_slot_text = "; ".join(
        f"{row['id']} = {row['name']} ({row['role']}; {row['distinction']})"
        for row in assigned_entities
    )
    return (
        f"{prompt} This is entity batch {batch_index + 1} of {batch_count}. "
        "Return only this batch's requested entities, with no overlap with earlier "
        f"batches. Earlier entities are: {exclusions or 'none'}. "
        "Use these preallocated entity IDs exactly, one per returned entity: "
        f"{', '.join(assigned_entity_ids) or 'no allocation supplied'}. "
        "Expand the allocated registry slots exactly; preserve each assigned name, "
        f"role, and distinction: {assigned_slot_text or 'no registry slot supplied'}."
    )


def _entity_registry_contract(
    expected_topic_id: str,
    *,
    expected_entity_ids: tuple[str, ...],
) -> StructuredContract[WorldForgeEntityRegistryResponse]:
    def validate_registry(value: WorldForgeEntityRegistryResponse) -> None:
        if value.topic_id != expected_topic_id:
            raise ValueError(
                f"World Forge registry returned {value.topic_id or '<missing>'} "
                f"for {expected_topic_id}"
            )
        actual_ids = tuple(row.id for row in value.entities)
        if set(actual_ids) != set(expected_entity_ids) or len(actual_ids) != len(
            set(actual_ids)
        ):
            raise ValueError(
                "World Forge registry returned IDs "
                f"{list(actual_ids)} for {expected_topic_id}; expected "
                f"{list(expected_entity_ids)}"
            )
        normalized_names = [row.name.strip().casefold() for row in value.entities]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError(
                f"World Forge registry returned duplicate names for {expected_topic_id}"
            )

    return StructuredContract(
        contract_id="rpg.world_forge.entity_registry",
        version=1,
        output_model=WorldForgeEntityRegistryResponse,
        semantic_validator=validate_registry,
        schema_profile="canon_strict",
        schema_name="rpg_world_forge_entity_registry",
    )


def _payload(
    node: CampaignTopicNode,
    *,
    seed: int,
    campaign_context: Mapping[str, Any],
    dependency_topics: Mapping[str, GeneratedTopic],
    batch_index: int | None = None,
    batch_count: int | None = None,
    existing_entities: tuple[Mapping[str, str], ...] = (),
    assigned_entity_ids: tuple[str, ...] = (),
    assigned_entities: tuple[Mapping[str, str], ...] = (),
) -> dict[str, Any]:
    payload = {
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
        "dependencies": _compact_dependency_topics(dependency_topics),
        "required_output": {
            "topic_id": node.topic_id,
            "collections": list(_COLLECTIONS),
            "entity_dossier": dossier_prompt_contract(node.topic_id),
        },
    }
    if batch_index is not None and batch_count is not None:
        payload["generation_batch"] = {
            "index": batch_index,
            "count": batch_count,
            "previous_entities": [dict(row) for row in existing_entities],
            "assigned_entity_ids": list(assigned_entity_ids),
            "assigned_entities": [dict(row) for row in assigned_entities],
        }
    return payload


def _entity_registry_system_prompt(node: CampaignTopicNode) -> str:
    return (
        "You are the Omnix Campaign World Forge planner. Return strict JSON only. "
        "Create a compact registry for the requested topic before any dossiers are "
        "written. Use every allocated ID exactly once. Give every entry a unique, "
        "setting-grounded name, role, and distinction so later parallel writers can "
        "expand different canon rather than inventing overlapping entities. Return "
        "only topic_id, entities, and provenance. Each entity must contain id, name, "
        "role, and distinction; do not write dossiers, facts, or documents. The "
        f"requested domain is {node.topic_id}."
    )


def _entity_registry_payload(
    node: CampaignTopicNode,
    *,
    seed: int,
    campaign_context: Mapping[str, Any],
    dependency_topics: Mapping[str, GeneratedTopic],
    assigned_entity_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "contract_version": "rpg_world_forge_entity_registry_request_v1",
        "seed": seed,
        "topic": {
            "topic_id": node.topic_id,
            "title": node.title,
            "category": node.category,
            "target_count": node.target_count,
            "metadata": dict(node.metadata),
        },
        "campaign_context": dict(campaign_context),
        "dependencies": _compact_dependency_topics(dependency_topics),
        "allocated_entity_ids": list(assigned_entity_ids),
        "required_output": {
            "topic_id": node.topic_id,
            "entity_fields": ["id", "name", "role", "distinction"],
        },
    }


def _compact_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _compact_entity_reference(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or row.get("entity_id") or ""),
        "name": _compact_text(row.get("name") or row.get("title"), limit=160),
        "kind": str(row.get("kind") or row.get("type") or ""),
        "summary": _compact_text(
            row.get("short_summary")
            or row.get("summary")
            or row.get("description"),
            limit=320,
        ),
    }


def _compact_dependency_topics(
    dependency_topics: Mapping[str, GeneratedTopic],
) -> dict[str, Any]:
    """Keep reference identity while excluding long dossiers from later prompts."""

    compact: dict[str, Any] = {}
    for topic_id, topic in sorted(dependency_topics.items()):
        compact[topic_id] = {
            "topic_id": topic.topic_id,
            "entities": [
                _compact_entity_reference(row)
                for row in topic.entities
            ],
            "facts": [
                {
                    "id": str(row.get("id") or row.get("fact_id") or ""),
                    "content": _compact_text(
                        row.get("content") or row.get("summary"),
                        limit=360,
                    ),
                    "entity_refs": [
                        str(value) for value in row.get("entity_refs") or ()
                    ][:20],
                }
                for row in topic.facts[:40]
            ],
            "relationships": [
                {
                    "source": str(row.get("source") or row.get("source_id") or ""),
                    "target": str(row.get("target") or row.get("target_id") or ""),
                    "kind": str(row.get("kind") or row.get("relationship") or ""),
                }
                for row in topic.relationships[:40]
            ],
            "documents": [
                {
                    "title": _compact_text(
                        row.get("title") or row.get("name"), limit=160
                    ),
                    "summary": _compact_text(
                        row.get("summary") or row.get("body") or row.get("text"),
                        limit=420,
                    ),
                }
                for row in topic.documents[:8]
            ],
        }
    return compact


def _token_estimate(text: str) -> int:
    """Return a deliberately labelled, provider-independent token estimate.

    Providers do not consistently return usage for structured completions.  This
    keeps durable world-generation records useful without presenting the value
    as metered provider usage.
    """

    return max(1, (len(text) + 3) // 4)


def _model_rows(rows: list[_WorldForgeRow]) -> tuple[Mapping[str, Any], ...]:
    return tuple(row.model_dump(mode="python") for row in rows)


class ProviderWorldForgeTopicGenerator:
    """Generate one validated canon topic through a request-local gateway."""

    def __init__(self, provider: BaseProvider, config: WorldForgeProviderConfig) -> None:
        self.transport_provider = provider
        self.provider = _ConfiguredProviderView(provider, config.provider)
        self.config = config
        self._progress_callback: Callable[[Mapping[str, Any]], None] | None = None

    def set_progress_callback(
        self,
        callback: Callable[[Mapping[str, Any]], None] | None,
    ) -> Callable[[Mapping[str, Any]], None] | None:
        """Install a request-local batch checkpoint hook and return the prior hook."""

        previous = self._progress_callback
        self._progress_callback = callback
        return previous

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        batch_size = min(self.config.entity_batch_size, node.target_count)
        if node.target_count <= batch_size:
            value, trusted, prompt_tokens, completion_tokens = self._generate_response(
                node,
                seed=seed,
                campaign_context=campaign_context,
                dependency_topics=dependency_topics,
            )
            generated = self._to_generated_topic(
                node,
                values=(value,),
                diagnostics=(trusted,),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            self._emit_progress(
                node,
                batch_current=1,
                batch_total=1,
                trusted=trusted,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            return generated

        batch_count = (node.target_count + batch_size - 1) // batch_size
        values: list[WorldForgeTopicResponse] = []
        registry, registry_diagnostics, prompt_tokens, completion_tokens = (
            self._generate_entity_registry(
                node,
                seed=seed,
                campaign_context=campaign_context,
                dependency_topics=dependency_topics,
            )
        )
        registry_slots = {row.id: row for row in registry.entities}
        diagnostics: list[Mapping[str, Any]] = [registry_diagnostics]
        existing_entities: list[Mapping[str, str]] = []
        batch_workers = min(self.config.entity_batch_workers, batch_count)
        for wave_start in range(0, batch_count, batch_workers):
            wave_indexes = tuple(
                range(wave_start, min(batch_count, wave_start + batch_workers))
            )
            # Batches in one wave intentionally share the same completed-entity
            # context.  The next wave receives every entity from this wave, keeping
            # prompts bounded while maintaining a two-call local-model pipeline.
            completed_entities = tuple(existing_entities)
            with ThreadPoolExecutor(max_workers=len(wave_indexes)) as executor:
                futures = {
                    batch_index: executor.submit(
                        self._generate_entity_batch,
                        node,
                        batch_index=batch_index,
                        batch_count=batch_count,
                        seed=seed,
                        campaign_context=campaign_context,
                        dependency_topics=dependency_topics,
                        existing_entities=completed_entities,
                        registry_slots=registry_slots,
                    )
                    for batch_index in wave_indexes
                }
                wave_results = {
                    batch_index: future.result()
                    for batch_index, future in futures.items()
                }
            self._validate_distinct_batch_entities(
                tuple(value for value, _, _, _ in wave_results.values()),
                existing_entities=completed_entities,
            )
            for batch_index in wave_indexes:
                value, trusted, batch_prompt_tokens, batch_completion_tokens = (
                    wave_results[batch_index]
                )
                values.append(value)
                diagnostics.append(trusted)
                prompt_tokens += batch_prompt_tokens
                completion_tokens += batch_completion_tokens
                self._emit_progress(
                    node,
                    batch_current=batch_index + 1,
                    batch_total=batch_count,
                    trusted=self._aggregate_usage(
                        tuple(dict(row.get("usage") or {}) for row in diagnostics)
                    ),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                existing_entities.extend(self._entity_identity_rows(value))
        self._validate_registry_alignment(values, registry.entities)
        return self._to_generated_topic(
            node,
            values=tuple(values),
            diagnostics=tuple(diagnostics),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            batch_size=batch_size,
            entity_registry=tuple(
                row.model_dump(mode="python") for row in registry.entities
            ),
        )

    def _generate_entity_batch(
        self,
        node: CampaignTopicNode,
        *,
        batch_index: int,
        batch_count: int,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
        existing_entities: tuple[Mapping[str, str], ...],
        registry_slots: Mapping[str, WorldForgeEntityRegistryItem],
    ) -> tuple[WorldForgeTopicResponse, Mapping[str, Any], int, int]:
        requested_count = min(
            self.config.entity_batch_size,
            node.target_count - batch_index * self.config.entity_batch_size,
        )
        assigned_entity_ids = self._assigned_entity_ids(
            node,
            batch_index=batch_index,
            requested_count=requested_count,
        )
        assigned_entities = tuple(
            registry_slots[entity_id].model_dump(mode="python")
            for entity_id in assigned_entity_ids
        )
        return self._generate_response(
            replace(node, target_count=requested_count),
            seed=seed + batch_index,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
            expected_entity_count=requested_count,
            expected_entity_ids=assigned_entity_ids,
            batch_index=batch_index,
            batch_count=batch_count,
            existing_entities=existing_entities,
            assigned_entity_ids=assigned_entity_ids,
            assigned_entities=assigned_entities,
        )

    def _generate_entity_registry(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> tuple[WorldForgeEntityRegistryResponse, Mapping[str, Any], int, int]:
        assigned_entity_ids = self._allocated_entity_ids(node)
        messages = [
            ChatMessage(role="system", content=_entity_registry_system_prompt(node)),
            ChatMessage(
                role="user",
                content=json.dumps(
                    _entity_registry_payload(
                        node,
                        seed=seed,
                        campaign_context=campaign_context,
                        dependency_topics=dependency_topics,
                        assigned_entity_ids=assigned_entity_ids,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        ]
        total_calls = max(1, self.config.max_retries + 2)
        gateway = StructuredOutputGateway(self.provider)
        provider_key = self.config.provider.strip().casefold().removeprefix("llm:")
        call_limiter = (
            _LMSTUDIO_WORLD_FORGE_CALLS
            if provider_key == "lmstudio"
            else nullcontext()
        )
        with call_limiter:
            outcome = gateway.try_generate(
                messages,
                contract=replace(
                    _entity_registry_contract(
                        node.topic_id,
                        expected_entity_ids=assigned_entity_ids,
                    ),
                    temperature=self.config.temperature,
                    max_tokens=min(self.config.max_tokens, 2048),
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
                f"structured World Forge registry provider failed for {node.topic_id} "
                f"after {diagnostics.provider_calls or total_calls} attempts: "
                f"{type(outcome.error).__name__}: {outcome.error}"
            ) from outcome.error
        assert outcome.value is not None
        registry_payload = json.dumps(
            outcome.value.model_dump(mode="python"),
            ensure_ascii=False,
            sort_keys=True,
        )
        prompt_tokens = sum(_token_estimate(message.content) for message in messages)
        completion_tokens = _token_estimate(registry_payload)
        return outcome.value, diagnostics.as_dict(), prompt_tokens, completion_tokens

    def _allocated_entity_ids(self, node: CampaignTopicNode) -> tuple[str, ...]:
        return self._assigned_entity_ids(
            node,
            batch_index=0,
            requested_count=node.target_count,
        )

    def _assigned_entity_ids(
        self,
        node: CampaignTopicNode,
        *,
        batch_index: int,
        requested_count: int,
    ) -> tuple[str, ...]:
        prefix = _ENTITY_ID_PREFIXES.get(node.topic_id, node.topic_id)
        first_index = batch_index * self.config.entity_batch_size + 1
        return tuple(
            f"ent:{prefix}:{entity_index:03d}"
            for entity_index in range(first_index, first_index + requested_count)
        )

    @staticmethod
    def _entity_identity_rows(
        value: WorldForgeTopicResponse,
    ) -> list[dict[str, str]]:
        return [
            {
                "id": str(row.get("id") or row.get("entity_id") or ""),
                "name": str(row.get("name") or row.get("title") or ""),
            }
            for row in _model_rows(value.entities)
        ]

    @classmethod
    def _validate_distinct_batch_entities(
        cls,
        values: tuple[WorldForgeTopicResponse, ...],
        *,
        existing_entities: tuple[Mapping[str, str], ...],
    ) -> None:
        seen = {
            (str(row.get("id") or "").casefold(), str(row.get("name") or "").casefold())
            for row in existing_entities
        }
        for value in values:
            for row in cls._entity_identity_rows(value):
                identity = (row["id"].casefold(), row["name"].casefold())
                if identity in seen:
                    raise RuntimeError(
                        "structured World Forge provider returned duplicate entity "
                        f"across concurrent batches: {row['id'] or row['name'] or '<unnamed>'}"
                    )
                seen.add(identity)

    @staticmethod
    def _validate_registry_alignment(
        values: list[WorldForgeTopicResponse],
        registry: list[WorldForgeEntityRegistryItem],
    ) -> None:
        expected = {row.id: row.name.strip() for row in registry}
        actual = {
            str(row.get("id") or row.get("entity_id") or ""): str(
                row.get("name") or row.get("title") or ""
            ).strip()
            for value in values
            for row in _model_rows(value.entities)
        }
        if actual != expected:
            raise RuntimeError(
                "structured World Forge merge does not match the entity registry"
            )

    @staticmethod
    def _apply_registry_slots(
        value: WorldForgeTopicResponse,
        assigned_entities: tuple[Mapping[str, str], ...],
    ) -> WorldForgeTopicResponse:
        """Make the compact registry authoritative for merge-critical identity.

        Some local models place a label only inside a dossier or summary.  The
        registry already validated a unique canonical name, so apply that value
        rather than rejecting otherwise valid dossier content for omitting a
        duplicate top-level field.
        """

        if not assigned_entities:
            return value
        slots = {str(row["id"]): row for row in assigned_entities}
        payload = value.model_dump(mode="python")
        for entity in payload["entities"]:
            entity_id = str(entity.get("id") or entity.get("entity_id") or "")
            slot = slots.get(entity_id)
            if slot is None:
                raise RuntimeError(
                    f"structured World Forge entity is outside its registry slot: {entity_id}"
                )
            entity["id"] = slot["id"]
            entity["entity_id"] = slot["id"]
            entity["name"] = slot["name"]
            entity["registry_role"] = slot["role"]
            entity["registry_distinction"] = slot["distinction"]
        return WorldForgeTopicResponse.model_validate(payload)

    def _emit_progress(
        self,
        node: CampaignTopicNode,
        *,
        batch_current: int,
        batch_total: int,
        trusted: Mapping[str, Any],
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        callback = self._progress_callback
        if callback is None:
            return
        usage = dict(trusted.get("usage") or trusted)
        provider_total = _token_usage_value(usage, "total_tokens", "total")
        provider_prompt = _token_usage_value(usage, "prompt_tokens", "input_tokens")
        provider_completion = _token_usage_value(
            usage,
            "completion_tokens",
            "output_tokens",
        )
        if provider_total:
            resolved_prompt = provider_prompt or prompt_tokens
            resolved_completion = provider_completion or completion_tokens
            total_tokens = provider_total
            source = "provider_reported"
        else:
            resolved_prompt = prompt_tokens
            resolved_completion = completion_tokens
            total_tokens = prompt_tokens + completion_tokens
            source = "estimated"
        try:
            callback(
                {
                    "topic_id": node.topic_id,
                    "batch_current": batch_current,
                    "batch_total": batch_total,
                    "token_usage": {
                        "prompt_tokens": resolved_prompt,
                        "completion_tokens": resolved_completion,
                        "total_tokens": total_tokens,
                        "source": source,
                    },
                }
            )
        except Exception:
            _LOGGER.warning(
                "world_forge_batch_progress_checkpoint_failed",
                exc_info=True,
                extra={"topic_id": node.topic_id},
            )

    def _generate_response(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
        expected_entity_count: int | None = None,
        expected_entity_ids: tuple[str, ...] = (),
        expected_entity_names: tuple[str, ...] = (),
        batch_index: int | None = None,
        batch_count: int | None = None,
        existing_entities: tuple[Mapping[str, str], ...] = (),
        assigned_entity_ids: tuple[str, ...] = (),
        assigned_entities: tuple[Mapping[str, str], ...] = (),
    ) -> tuple[WorldForgeTopicResponse, Mapping[str, Any], int, int]:
        messages = [
            ChatMessage(
                role="system",
                content=_system_prompt(
                    node,
                    batch_index=batch_index,
                    batch_count=batch_count,
                    existing_entities=existing_entities,
                    assigned_entity_ids=assigned_entity_ids,
                    assigned_entities=assigned_entities,
                ),
            ),
            ChatMessage(
                role="user",
                content=json.dumps(
                    _payload(
                        node,
                        seed=seed,
                        campaign_context=campaign_context,
                        dependency_topics=dependency_topics,
                        batch_index=batch_index,
                        batch_count=batch_count,
                        existing_entities=existing_entities,
                        assigned_entity_ids=assigned_entity_ids,
                        assigned_entities=assigned_entities,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        ]
        total_calls = max(1, self.config.max_retries + 2)
        gateway = StructuredOutputGateway(self.provider)
        provider_key = self.config.provider.strip().casefold().removeprefix("llm:")
        call_limiter = (
            _LMSTUDIO_WORLD_FORGE_CALLS
            if provider_key == "lmstudio"
            else nullcontext()
        )
        with call_limiter:
            outcome = gateway.try_generate(
                messages,
                contract=replace(
                    _topic_contract(
                    node.topic_id,
                    expected_entity_count=expected_entity_count,
                    expected_entity_ids=expected_entity_ids,
                    expected_entity_names=expected_entity_names,
                    ),
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
            batch_label = (
                f" batch {batch_index + 1}/{batch_count}"
                if batch_index is not None and batch_count is not None
                else ""
            )
            raise RuntimeError(
                f"structured World Forge provider failed for {node.topic_id}{batch_label} "
                f"after {diagnostics.provider_calls or total_calls} attempts: "
                f"{type(outcome.error).__name__}: {outcome.error}"
            ) from outcome.error
        assert outcome.value is not None
        value = self._apply_registry_slots(outcome.value, assigned_entities)
        trusted = diagnostics.as_dict()
        generated_payload = json.dumps(
            value.model_dump(mode="python"),
            ensure_ascii=False,
            sort_keys=True,
        )
        prompt_tokens_estimate = sum(_token_estimate(message.content) for message in messages)
        completion_tokens_estimate = _token_estimate(generated_payload)
        return value, trusted, prompt_tokens_estimate, completion_tokens_estimate

    def _to_generated_topic(
        self,
        node: CampaignTopicNode,
        *,
        values: tuple[WorldForgeTopicResponse, ...],
        diagnostics: tuple[Mapping[str, Any], ...],
        prompt_tokens: int,
        completion_tokens: int,
        batch_size: int | None = None,
        entity_registry: tuple[Mapping[str, Any], ...] = (),
    ) -> GeneratedTopic:
        assert values and diagnostics
        trusted = diagnostics[-1]
        provider_provenance = dict(values[0].provenance)
        batch_count = len(values)
        if batch_count > 1:
            provider_provenance["entity_batches"] = {
                "strategy": "sequential_entity_batches",
                "batch_count": batch_count,
                "batch_size": batch_size,
                "target_count": node.target_count,
            }
        if entity_registry:
            provider_provenance["entity_registry"] = {
                "contract": "rpg_world_forge_entity_registry_v1",
                "entities": [dict(row) for row in entity_registry],
            }
        usage = self._aggregate_usage(
            tuple(dict(row.get("usage") or {}) for row in diagnostics)
        )
        return GeneratedTopic(
            topic_id=node.topic_id,
            documents=tuple(
                row for value in values for row in _model_rows(value.documents)
            ),
            entities=tuple(
                row for value in values for row in _model_rows(value.entities)
            ),
            facts=tuple(row for value in values for row in _model_rows(value.facts)),
            relationships=tuple(
                row for value in values for row in _model_rows(value.relationships)
            ),
            knowledge_rules=tuple(
                row for value in values for row in _model_rows(value.knowledge_rules)
            ),
            story_threads=tuple(
                row for value in values for row in _model_rows(value.story_threads)
            ),
            provenance={
                **provider_provenance,
                "generator": "structured_world_forge_provider_v1",
                "provider_contract": "rpg_world_forge_topic_request_v3",
                "provider": self.config.provider,
                "model": self.config.model,
                "attempt_count": sum(
                    int(row.get("provider_calls") or 1) for row in diagnostics
                ),
                "latency_ms": round(
                    sum(float(row.get("latency_ms") or 0.0) for row in diagnostics),
                    3,
                ),
                "usage": usage,
                "token_estimate": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "method": "characters_divided_by_4",
                },
                "finish_reason": str(trusted.get("finish_reason") or ""),
                "entity_dossier_schema": "rpg_world_entity_dossier_v1",
                "response_format": str(trusted.get("selected_mode") or ""),
                "structured_contract": "rpg.world_forge.topic.v3",
                "schema_hash": str(trusted.get("schema_hash") or ""),
                "max_tokens": self.config.max_tokens,
            },
        )

    @staticmethod
    def _aggregate_usage(values: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
        totals: dict[str, Any] = {}
        for value in values:
            for key, item in value.items():
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    totals[key] = totals.get(key, 0) + item
        return totals


def _token_usage_value(usage: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            value = max(0, int(usage.get(key) or 0))
        except (TypeError, ValueError):
            value = 0
        if value:
            return value
    return 0


def attach_world_forge_progress_callback(
    generator: Any,
    callback: Callable[[Mapping[str, Any]], None],
) -> Callable[[], None]:
    """Attach a checkpoint callback through production generator wrappers.

    The production route can wrap a provider generator in validation, reference-safe,
    and fallback adapters.  This keeps batch checkpoints independent of that wiring.
    """

    configured: list[
        tuple[ProviderWorldForgeTopicGenerator, Callable[[Mapping[str, Any]], None] | None]
    ] = []
    visited: set[int] = set()

    def visit(value: Any) -> None:
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if isinstance(value, ProviderWorldForgeTopicGenerator):
            configured.append((value, value.set_progress_callback(callback)))
            return
        nested = getattr(value, "generator", None)
        if nested is not None:
            visit(nested)
        for nested_generator in getattr(value, "generators", ()):
            visit(nested_generator)

    visit(generator)

    def detach() -> None:
        for provider, previous in configured:
            provider.set_progress_callback(previous)

    return detach


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
