from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds import generation_retry
from app.rpg.worlds.generation_candidate_spool import (
    delete_candidate_spool,
    write_candidate_spool,
)
from app.rpg.worlds.generation_jobs import (
    WorldTopicGenerationSettings,
    canonical_hash,
)
from app.rpg.worlds.generation_worker import _release_interrupted_job


def _run() -> dict:
    graph = CampaignTopicGraph(
        graph_version="test-v1",
        campaign_template="test",
        depth="quick",
        nodes=(CampaignTopicNode("rules", "Rules", "lore"),),
    )
    settings = WorldTopicGenerationSettings(
        generator_version="g1",
        prompt_version="p1",
        provider_route="lmstudio",
        model="model",
        seed=1,
    )
    return {
        "run_id": "run:child",
        "world_id": "world:1",
        "draft_revision": 1,
        "graph": graph.as_dict(),
        "context": {
            "scope": {
                "retry_of_run_id": "run:parent",
                "decision_topic_ids": ["rules"],
            },
            "generation_context": {},
            "topic_directives": {"rules": {"manual_retry": {"parent_run_id": "run:parent"}}},
            "entity_manifest_hash": "sha256:manifest",
            "target_topic_ids": ["rules"],
        },
        "settings": settings.as_dict(),
        "plan": {},
        "progress": {
            "flagged_topic_ids": ["rules"],
            "failed_topic_ids": [],
            "blocked_topic_ids": [],
        },
        "lineage": {"manual_retry": True},
    }


def _result() -> dict:
    candidate = GeneratedTopic(
        topic_id="rules",
        entities=({"id": "rule:1", "kind": "rule", "rule": "No drones after dusk."},),
        provenance={
            "generation_review": {
                "status": "needs_review",
                "reason_codes": ["manual_retry_decision_required"],
            }
        },
    ).as_dict()
    return {
        "topic_id": "rules",
        "status": "needs_review",
        "candidate": candidate,
        "candidate_hash": canonical_hash(candidate),
        "validation": {
            "reason_codes": ["manual_retry_decision_required"],
            "issues": [],
        },
        "dependency_hashes": {},
        "dependency_trust": {},
    }


class _GenerationRepository:
    def __init__(self) -> None:
        self.run = _run()
        self.result = _result()
        self.updated: dict | None = None

    def get(self, context, run_id):
        del context, run_id
        return self.run

    def get_topic_result(self, context, *, run_id, topic_id):
        del context, run_id, topic_id
        return self.result

    def update(self, context, **kwargs):
        del context
        self.updated = kwargs
        self.run = {
            **self.run,
            "plan": kwargs.get("plan", self.run["plan"]),
            "progress": kwargs.get("progress", self.run["progress"]),
        }
        return self.run


class _ScenarioRepository:
    def __init__(self) -> None:
        self.promotions: list[dict] = []

    def put_topic(self, context, **kwargs):
        del context
        self.promotions.append(kwargs)
        return kwargs


class _Work:
    def __init__(self) -> None:
        self.world_generation = _GenerationRepository()
        self.world_scenarios = _ScenarioRepository()
        self.committed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        del args


def test_keep_decision_does_not_promote_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    work = _Work()
    monkeypatch.setattr(generation_retry, "bootstrap_local_tenant", lambda database: object())
    monkeypatch.setattr(generation_retry, "unit_of_work", lambda database: work)
    monkeypatch.setattr(
        generation_retry,
        "reconcile_world_generation",
        lambda run_id, database=None: work.world_generation.run,
    )
    result = generation_retry.decide_world_generation_retry(
        "run:child",
        "rules",
        decision="keep",
    )
    assert result["decision"] == "keep"
    assert work.world_scenarios.promotions == []
    assert work.world_generation.updated is not None
    assert work.world_generation.updated["plan"]["review_decisions"]["rules"]["decision"] == "keep"


def test_replace_decision_promotes_only_after_explicit_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = _Work()
    monkeypatch.setattr(generation_retry, "bootstrap_local_tenant", lambda database: object())
    monkeypatch.setattr(generation_retry, "unit_of_work", lambda database: work)
    monkeypatch.setattr(
        generation_retry,
        "reconcile_world_generation",
        lambda run_id, database=None: work.world_generation.run,
    )
    result = generation_retry.decide_world_generation_retry(
        "run:child",
        "rules",
        decision="replace",
    )
    assert result["decision"] == "replace"
    assert len(work.world_scenarios.promotions) == 1
    promotion = work.world_scenarios.promotions[0]
    assert promotion["topic_id"] == "rules"
    assert promotion["status"] == "ready"
    assert result["decision_record"]["promoted_hash"] == promotion["content_hash"]


@dataclass
class _Cursor:
    rowcount: int = 1


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return _Cursor()


class _RecoveryWork:
    def __init__(self) -> None:
        self.connection = _Connection()


def test_spooled_persistence_replay_extends_queue_attempt_budget(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_RPG_WORLD_GENERATION_SPOOL_DIR", str(tmp_path))
    write_candidate_spool(
        "job:rules",
        {"run_id": "run:1", "topic_id": "rules", "candidate": {"topic_id": "rules"}},
    )
    work = _RecoveryWork()
    context = type("Context", (), {"workspace_id": "workspace:1"})()
    retryable = _release_interrupted_job(
        work,
        context,
        job_id="job:rules",
        job_type="rpg.world.topic.generate",
        attempt_count=2,
        max_attempts=2,
        error_code="database_unavailable",
    )
    assert retryable is True
    params = work.connection.calls[0][1]
    assert params[0] == "retrying"
    assert params[1] == 3
    assert params[4] == "persist_existing_spool"
    delete_candidate_spool("job:rules")
