"""Deterministic durable-job planning for reusable-world topic generation."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.jobs.models import ResourceClass
from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)

WORLD_TOPIC_JOB_TYPE = "rpg.world.topic.generate"
WORLD_TOPIC_RESOURCE_CLASS = ResourceClass.RPG_WORLD_GENERATION.value
WORLD_TOPIC_JOB_CONTRACT = "rpg_world_topic_job_v1"
WORLD_TOPIC_OUTPUT_SCHEMA = "rpg_world_topic_output_v1"
_NON_GENERATION_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.:-]+")


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def world_generation_run_id(
    *,
    world_id: str,
    draft_revision: int,
) -> str:
    safe_world = _SAFE_ID.sub("-", world_id).strip("-")
    return f"world-generation:{safe_world}:draft:{int(draft_revision)}"


@dataclass(frozen=True)
class WorldTopicGenerationSettings:
    generator_version: str
    prompt_version: str
    provider_route: str
    model: str
    seed: int
    topic_contract_version: str = WORLD_TOPIC_JOB_CONTRACT
    output_schema_version: str = WORLD_TOPIC_OUTPUT_SCHEMA
    compiler_version: str = "world-compiler-v1"
    max_attempts: int = 3
    priority: int = 10

    def as_dict(self) -> dict[str, Any]:
        return {
            "generator_version": self.generator_version,
            "prompt_version": self.prompt_version,
            "provider_route": self.provider_route,
            "model": self.model,
            "seed": int(self.seed),
            "topic_contract_version": self.topic_contract_version,
            "output_schema_version": self.output_schema_version,
            "compiler_version": self.compiler_version,
            "max_attempts": max(1, int(self.max_attempts)),
            "priority": int(self.priority),
        }


@dataclass(frozen=True)
class WorldTopicJobPlan:
    run_id: str
    world_id: str
    draft_revision: int
    topic_id: str
    dependency_ids: tuple[str, ...]
    dependency_hashes: Mapping[str, str]
    directive_hash: str
    input_hash: str
    fingerprint: str
    job_id: str
    job_payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "world_id": self.world_id,
            "draft_revision": self.draft_revision,
            "topic_id": self.topic_id,
            "dependency_ids": list(self.dependency_ids),
            "dependency_hashes": dict(self.dependency_hashes),
            "directive_hash": self.directive_hash,
            "input_hash": self.input_hash,
            "fingerprint": self.fingerprint,
            "job_id": self.job_id,
            "job_payload": dict(self.job_payload),
        }


def topic_generation_fingerprint(
    node: CampaignTopicNode,
    *,
    normalized_topic_input: Mapping[str, Any],
    dependency_hashes: Mapping[str, str],
    directives: Mapping[str, Any],
    entity_manifest_hash: str,
    settings: WorldTopicGenerationSettings,
) -> tuple[str, str, str]:
    topic_input = {
        "node": node.as_dict(),
        "input": dict(normalized_topic_input),
    }
    input_hash = canonical_hash(topic_input)
    directive_hash = canonical_hash(dict(directives))
    fingerprint_payload = {
        "topic_id": node.topic_id,
        "input_hash": input_hash,
        "dependency_hashes": dict(sorted(dependency_hashes.items())),
        "directive_hash": directive_hash,
        "entity_manifest_hash": entity_manifest_hash,
        **settings.as_dict(),
    }
    return canonical_hash(fingerprint_payload), input_hash, directive_hash


def world_topic_job_id(
    *,
    world_id: str,
    draft_revision: int,
    topic_id: str,
    fingerprint: str,
) -> str:
    safe_world = _SAFE_ID.sub("-", world_id).strip("-")
    safe_topic = _SAFE_ID.sub("-", topic_id).strip("-")
    digest = fingerprint.removeprefix("sha256:")[:20]
    return (
        f"world-topic:{safe_world}:draft:{int(draft_revision)}:"
        f"{safe_topic}:{digest}"
    )


def plan_ready_topic_jobs(
    graph: CampaignTopicGraph,
    *,
    run_id: str,
    world_id: str,
    draft_revision: int,
    generation_context: Mapping[str, Any],
    topic_directives: Mapping[str, Mapping[str, Any]],
    completed_topics: Mapping[str, Mapping[str, Any]],
    existing_job_ids: Sequence[str],
    entity_manifest_hash: str,
    settings: WorldTopicGenerationSettings,
) -> tuple[WorldTopicJobPlan, ...]:
    existing = set(existing_job_ids)
    completed_ids = {
        topic_id
        for topic_id, row in completed_topics.items()
        if str(row.get("status") or "") == "ready" and row.get("content_hash")
    }
    plans: list[WorldTopicJobPlan] = []
    for node in graph.topological_order():
        if node.category in _NON_GENERATION_CATEGORIES:
            continue
        if node.topic_id in completed_ids:
            continue
        if not set(node.dependencies).issubset(completed_ids):
            continue
        dependency_hashes = {
            dependency_id: str(completed_topics[dependency_id]["content_hash"])
            for dependency_id in node.dependencies
        }
        directives = dict(topic_directives.get(node.topic_id) or {})
        fingerprint, input_hash, directive_hash = topic_generation_fingerprint(
            node,
            normalized_topic_input={
                "generation_context": dict(generation_context),
                "target_count": node.target_count,
                "visibility": node.visibility,
            },
            dependency_hashes=dependency_hashes,
            directives=directives,
            entity_manifest_hash=entity_manifest_hash,
            settings=settings,
        )
        job_id = world_topic_job_id(
            world_id=world_id,
            draft_revision=draft_revision,
            topic_id=node.topic_id,
            fingerprint=fingerprint,
        )
        if job_id in existing:
            continue
        input_payload = {
            "contract_version": WORLD_TOPIC_JOB_CONTRACT,
            "run_id": run_id,
            "world_id": world_id,
            "draft_revision": int(draft_revision),
            "topic": node.as_dict(),
            "generation_context": dict(generation_context),
            "directives": directives,
            "dependency_hashes": dependency_hashes,
            "fingerprint": fingerprint,
            "input_hash": input_hash,
            "directive_hash": directive_hash,
            "entity_manifest_hash": entity_manifest_hash,
            "settings": settings.as_dict(),
        }
        job_payload = {
            "id": job_id,
            "module": "rpg",
            "job_type": WORLD_TOPIC_JOB_TYPE,
            "resource_class": WORLD_TOPIC_RESOURCE_CLASS,
            "priority": settings.priority,
            "max_attempts": settings.max_attempts,
            "input_payload": input_payload,
            "metadata": {
                "contract_version": WORLD_TOPIC_JOB_CONTRACT,
                "run_id": run_id,
                "world_id": world_id,
                "draft_revision": int(draft_revision),
                "topic_id": node.topic_id,
                "fingerprint": fingerprint,
                "dependency_ids": list(node.dependencies),
            },
        }
        plans.append(
            WorldTopicJobPlan(
                run_id=run_id,
                world_id=world_id,
                draft_revision=int(draft_revision),
                topic_id=node.topic_id,
                dependency_ids=node.dependencies,
                dependency_hashes=dependency_hashes,
                directive_hash=directive_hash,
                input_hash=input_hash,
                fingerprint=fingerprint,
                job_id=job_id,
                job_payload=job_payload,
            )
        )
    return tuple(plans)


def generation_progress(
    graph: CampaignTopicGraph,
    *,
    completed_topic_ids: Sequence[str],
    active_topic_ids: Sequence[str],
    failed_topic_ids: Sequence[str] = (),
) -> dict[str, Any]:
    generation_ids = [
        node.topic_id
        for node in graph.topological_order()
        if node.category not in _NON_GENERATION_CATEGORIES
    ]
    completed = set(completed_topic_ids)
    failed = set(failed_topic_ids)
    total = len(generation_ids)
    complete_count = len(completed.intersection(generation_ids))
    return {
        "total_topics": total,
        "completed_topics": complete_count,
        "active_topic_ids": sorted(set(active_topic_ids)),
        "failed_topic_ids": sorted(failed),
        "percent": 100 if total == 0 else round(complete_count / total * 100),
        "generation_complete": complete_count == total and not failed,
    }
