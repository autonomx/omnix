"""Parallel, dependency-aware World Forge topic generation.

Generation is provider-pluggable. Hosted tests use the deterministic generator;
production may inject a Hermes/model-backed generator that returns the same
structured topic contract.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .world_forge_contract import CampaignTopicGraph, CampaignTopicNode


@dataclass(frozen=True)
class GeneratedTopic:
    topic_id: str
    documents: tuple[Mapping[str, Any], ...] = ()
    entities: tuple[Mapping[str, Any], ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    relationships: tuple[Mapping[str, Any], ...] = ()
    knowledge_rules: tuple[Mapping[str, Any], ...] = ()
    story_threads: tuple[Mapping[str, Any], ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "documents": [dict(row) for row in self.documents],
            "entities": [dict(row) for row in self.entities],
            "facts": [dict(row) for row in self.facts],
            "relationships": [dict(row) for row in self.relationships],
            "knowledge_rules": [dict(row) for row in self.knowledge_rules],
            "story_threads": [dict(row) for row in self.story_threads],
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GeneratedTopic":
        def rows(name: str) -> tuple[Mapping[str, Any], ...]:
            return tuple(
                dict(row)
                for row in value.get(name) or ()
                if isinstance(row, Mapping)
            )

        return cls(
            topic_id=str(value.get("topic_id") or ""),
            documents=rows("documents"),
            entities=rows("entities"),
            facts=rows("facts"),
            relationships=rows("relationships"),
            knowledge_rules=rows("knowledge_rules"),
            story_threads=rows("story_threads"),
            provenance=dict(value.get("provenance") or {}),
        )


@dataclass(frozen=True)
class WorldForgeJobRecord:
    topic_id: str
    status: str
    dependency_ids: tuple[str, ...]
    generator_role: str
    output_counts: Mapping[str, int] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "status": self.status,
            "dependency_ids": list(self.dependency_ids),
            "generator_role": self.generator_role,
            "output_counts": dict(self.output_counts),
            "error": self.error,
        }


@dataclass(frozen=True)
class WorldForgeGenerationResult:
    topics: tuple[GeneratedTopic, ...]
    jobs: tuple[WorldForgeJobRecord, ...]
    failed_topic_ids: tuple[str, ...]
    generation_order: tuple[tuple[str, ...], ...]

    @property
    def passed(self) -> bool:
        return not self.failed_topic_ids

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "topics": [topic.as_dict() for topic in self.topics],
            "jobs": [job.as_dict() for job in self.jobs],
            "failed_topic_ids": list(self.failed_topic_ids),
            "generation_order": [list(batch) for batch in self.generation_order],
        }


class WorldForgeTopicGenerator(Protocol):
    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic: ...


_NON_GENERATION_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}


def _counts(topic: GeneratedTopic) -> dict[str, int]:
    return {
        "documents": len(topic.documents),
        "entities": len(topic.entities),
        "facts": len(topic.facts),
        "relationships": len(topic.relationships),
        "knowledge_rules": len(topic.knowledge_rules),
        "story_threads": len(topic.story_threads),
    }


def _default_generator() -> WorldForgeTopicGenerator:
    from .world_forge_deterministic import DeterministicWorldForgeGenerator

    return DeterministicWorldForgeGenerator()


def generate_campaign_topics(
    graph: CampaignTopicGraph,
    *,
    generator: WorldForgeTopicGenerator | None = None,
    seed: int = 0,
    campaign_context: Mapping[str, Any] | None = None,
    max_parallel_jobs: int = 4,
    existing_topics: Mapping[str, GeneratedTopic] | None = None,
) -> WorldForgeGenerationResult:
    """Generate independent ready topics in parallel while preserving dependencies."""

    selected_generator = generator or _default_generator()
    context = dict(campaign_context or {})
    node_map = graph.node_map()
    topics: dict[str, GeneratedTopic] = dict(existing_topics or {})
    pending = {
        node.topic_id: set(node.dependencies)
        for node in graph.nodes
        if node.category not in _NON_GENERATION_CATEGORIES
        and node.topic_id not in topics
    }
    jobs: dict[str, WorldForgeJobRecord] = {
        topic_id: WorldForgeJobRecord(
            topic_id,
            "completed",
            node_map[topic_id].dependencies,
            node_map[topic_id].generator_role,
            _counts(topic),
        )
        for topic_id, topic in topics.items()
        if topic_id in node_map
    }
    batches: list[tuple[str, ...]] = []
    workers = max(1, min(int(max_parallel_jobs), 4))
    while pending:
        ready = tuple(
            sorted(
                topic_id
                for topic_id, dependencies in pending.items()
                if dependencies.intersection(pending) == set()
                and dependencies.issubset(set(topics).union(_NON_GENERATION_CATEGORIES))
            )
        )
        if not ready:
            ready = tuple(
                sorted(
                    topic_id
                    for topic_id, dependencies in pending.items()
                    if all(dep in topics or dep not in pending for dep in dependencies)
                )
            )
        if not ready:
            unresolved = ",".join(sorted(pending))
            raise ValueError(f"World Forge generation dependencies cannot be resolved: {unresolved}")
        batches.append(ready)
        with ThreadPoolExecutor(max_workers=min(workers, len(ready))) as executor:
            futures = {}
            for topic_id in ready:
                node = node_map[topic_id]
                dependencies = {dep: topics[dep] for dep in node.dependencies if dep in topics}
                future = executor.submit(
                    selected_generator.generate,
                    node,
                    seed=seed,
                    campaign_context=context,
                    dependency_topics=dependencies,
                )
                futures[future] = node
            for future in as_completed(futures):
                node = futures[future]
                try:
                    topic = future.result()
                    if topic.topic_id != node.topic_id:
                        raise ValueError(f"generator returned {topic.topic_id} for {node.topic_id}")
                    topics[node.topic_id] = topic
                    jobs[node.topic_id] = WorldForgeJobRecord(
                        node.topic_id,
                        "completed",
                        node.dependencies,
                        node.generator_role,
                        _counts(topic),
                    )
                except Exception as exc:
                    jobs[node.topic_id] = WorldForgeJobRecord(
                        node.topic_id,
                        "failed",
                        node.dependencies,
                        node.generator_role,
                        error=str(exc),
                    )
        for topic_id in ready:
            pending.pop(topic_id, None)
        failed = {topic_id for topic_id in ready if topic_id not in topics}
        if failed:
            for topic_id, dependencies in list(pending.items()):
                if dependencies.intersection(failed):
                    node = node_map[topic_id]
                    jobs[topic_id] = WorldForgeJobRecord(
                        topic_id,
                        "blocked",
                        node.dependencies,
                        node.generator_role,
                        error="dependency_failed",
                    )
                    pending.pop(topic_id)
            break
    ordered_topics = tuple(
        topics[node.topic_id]
        for node in graph.topological_order()
        if node.topic_id in topics
    )
    ordered_jobs = tuple(jobs[topic_id] for topic_id in sorted(jobs))
    failed_ids = tuple(sorted(job.topic_id for job in ordered_jobs if job.status != "completed"))
    return WorldForgeGenerationResult(
        ordered_topics,
        ordered_jobs,
        failed_ids,
        tuple(batches),
    )
