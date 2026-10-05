from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds import generation_publication_guard as publication_guard
from app.rpg.worlds.generation_candidate_spool import (
    delete_provider_started_spool,
    delete_raw_candidate_spool,
    read_raw_candidate_spool,
    write_provider_started_spool,
)
from app.rpg.worlds.generation_failure_spool import ReplayedGenerationFailure
from app.rpg.worlds.generation_jobs import (
    WorldTopicGenerationSettings,
    topic_generation_fingerprint,
)
from app.rpg.worlds.generation_review_analytics import (
    world_generation_review_analytics,
)
from app.rpg.worlds.generation_worker import _topic_generator_for_job


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="test-v1",
        campaign_template="test",
        depth="quick",
        nodes=(
            CampaignTopicNode("rules", "Rules", "lore"),
            CampaignTopicNode("actors", "Actors", "lore", dependencies=("rules",)),
            CampaignTopicNode("threads", "Threads", "lore", dependencies=("actors",)),
            CampaignTopicNode("places", "Places", "lore"),
        ),
    )


def test_prompt_only_retry_evidence_does_not_change_reuse_fingerprint() -> None:
    node = CampaignTopicNode("actors", "Actors", "lore")
    settings = WorldTopicGenerationSettings(
        generator_version="g1",
        prompt_version="p1",
        provider_route="lmstudio",
        model="model",
        seed=3,
    )
    common = dict(
        normalized_topic_input={"generation_context": {}, "target_count": 1},
        dependency_hashes={},
        entity_manifest_hash="sha256:manifest",
        settings=settings,
    )
    plain = topic_generation_fingerprint(node, directives={"tone": "tense"}, **common)
    retry = topic_generation_fingerprint(
        node,
        directives={
            "tone": "tense",
            "manual_retry": {
                "parent_run_id": "run:old",
                "prior_candidate": {"topic_id": "actors"},
                "issues": [{"code": "invalid"}],
            },
        },
        **common,
    )
    assert plain == retry


class _ProviderCandidate:
    def __init__(self, topic: GeneratedTopic) -> None:
        self.topic = topic
        self.calls = 0

    def generate(self, node, *, seed, campaign_context, dependency_topics):
        del node, seed, campaign_context, dependency_topics
        self.calls += 1
        return self.topic


def _job(attempt_count: int = 2) -> dict:
    return {
        "id": "job:actors",
        "attempt_count": attempt_count,
        "input_payload": {
            "run_id": "run:1",
            "world_id": "world:1",
            "draft_revision": 1,
            "topic": {"topic_id": "actors"},
            "dependency_hashes": {},
            "dependency_trust": {},
            "settings": {},
        },
    }


def test_later_lease_may_call_provider_when_started_marker_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_RPG_WORLD_GENERATION_SPOOL_DIR", str(tmp_path))
    underlying = _ProviderCandidate(GeneratedTopic(topic_id="actors"))
    generator = _topic_generator_for_job(_job(), underlying)
    result = generator.generate(
        CampaignTopicNode("actors", "Actors", "lore"),
        seed=1,
        campaign_context={},
        dependency_topics={},
    )
    assert result.topic_id == "actors"
    assert underlying.calls == 1
    assert read_raw_candidate_spool("job:actors") is not None
    delete_raw_candidate_spool("job:actors")
    delete_provider_started_spool("job:actors")


def test_started_provider_without_spool_fails_closed_without_another_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_RPG_WORLD_GENERATION_SPOOL_DIR", str(tmp_path))
    write_provider_started_spool(
        "job:actors",
        {"run_id": "run:1", "world_id": "world:1", "topic_id": "actors"},
    )
    underlying = _ProviderCandidate(GeneratedTopic(topic_id="actors"))
    generator = _topic_generator_for_job(_job(), underlying)
    with pytest.raises(ReplayedGenerationFailure, match="spool_missing"):
        generator.generate(
            CampaignTopicNode("actors", "Actors", "lore"),
            seed=1,
            campaign_context={},
            dependency_topics={},
        )
    assert underlying.calls == 0
    delete_provider_started_spool("job:actors")


class _GuardRepository:
    def get(self, context, run_id):
        del context
        return {
            "run_id": run_id,
            "world_id": "world:1",
            "draft_revision": 1,
            "context": {"target_topic_ids": ["rules"]},
            "graph": _graph().as_dict(),
            "plan": {},
            "lineage": {},
        }

    def list_topic_results(self, context, *, run_id):
        del context, run_id
        return [
            {
                "topic_id": "rules",
                "status": "accepted",
                "candidate_hash": "sha256:new-rules",
                "validation": {"reason_codes": []},
            }
        ]

    def list_topics(self, context, *, world_id, draft_revision):
        del context, world_id, draft_revision
        return [
            {
                "topic_id": "rules",
                "status": "ready",
                "source": "ai",
                "content_hash": "sha256:new-rules",
                "dependency_hashes": {},
            },
            {
                "topic_id": "actors",
                "status": "ready",
                "source": "ai",
                "content_hash": "sha256:actors",
                "dependency_hashes": {"rules": "sha256:old-rules"},
            },
            {
                "topic_id": "threads",
                "status": "ready",
                "source": "ai",
                "content_hash": "sha256:threads",
                "dependency_hashes": {"actors": "sha256:actors"},
            },
            {
                "topic_id": "places",
                "status": "ready",
                "source": "ai",
                "content_hash": "sha256:places",
                "dependency_hashes": {},
            },
        ]


class _GuardWork:
    world_generation = _GuardRepository()

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        del args


def test_publication_blocks_stale_transitive_dependent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.security.tenant_context import local_tenant_context

    monkeypatch.setattr(publication_guard, "current_tenant", local_tenant_context)
    monkeypatch.setattr(publication_guard, "unit_of_work", lambda database: _GuardWork())
    report = publication_guard.publication_review_report("run:child")
    assert report["publishable"] is False
    assert report["dependency_hash_mismatches"] == [
        {
            "topic_id": "actors",
            "dependency_id": "rules",
            "stored_hash": "sha256:old-rules",
            "current_hash": "sha256:new-rules",
        }
    ]


def test_analytics_include_domain_model_and_prompt_version() -> None:
    analytics = world_generation_review_analytics(
        [
            {
                "topic_id": "actors",
                "status": "needs_review",
                "provider": {"model": "qwen", "provider": "lmstudio"},
                "validation": {
                    "issues": [
                        {
                            "code": "missing_required_structured_field",
                            "topic_id": "actors",
                            "field_id": "motivation",
                        }
                    ]
                },
            }
        ],
        {"settings": {"prompt_version": "world-prompt-v9"}},
    )
    assert analytics["by_domain"] == {"actors": 1}
    assert analytics["by_model"] == {"qwen": 1}
    assert analytics["by_prompt_version"] == {"world-prompt-v9": 1}
