from __future__ import annotations

import json

import pytest

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_dossiers import dossier_prompt_contract
from app.rpg.worlds import generation_acceptance
from app.rpg.worlds.generation_authorship_policy_signing import (
    bind_signed_authorship_policy,
)
from app.rpg.worlds.generation_authorship_runtime import build_generation_artifact
from app.rpg.worlds.generation_authorship_signing import (
    attach_signed_llm_authorship,
    harden_and_sign_generation_artifact,
    sign_record,
)
from app.rpg.worlds.generation_jobs import WorldTopicGenerationSettings, canonical_hash
from app.rpg.worlds.generation_contract_receipt import (
    RECEIPT_SCHEMA_VERSION,
    canonical_candidate_content_hash,
)


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OMNIX_RPG_AUTHORSHIP_SIGNING_KEY",
        "test-only-world-review-signing-key-with-more-than-thirty-two-bytes",
    )


def _candidate(topic_id: str, entity_id: str, name: str) -> dict:
    dossier_sections = (
        dossier_prompt_contract(topic_id)["entity_fields"]["dossier"]["sections"]
    )
    candidate = GeneratedTopic(
        topic_id=topic_id,
        entities=(
            {
                "id": entity_id,
                "kind": topic_id.rstrip("s"),
                "name": name,
                "description": f"Lore for {name}.",
                "short_summary": f"Lore for {name}.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "sections": [
                        {
                            "id": section["id"],
                            "title": section["title"],
                            "paragraphs": [f"Long-form lore for {name}."],
                        }
                        for section in dossier_sections
                    ],
                },
            },
        ),
        provenance={
            "generator": "structured_world_forge_provider_v1",
            "provider": "lmstudio",
            "model": "model",
            "raw_response_hash": "a" * 64,
            "raw_response_hash_kind": "provider_response",
            "generation_status": "needs_review",
            "generation_review": {
                "status": "needs_review",
                "reason_codes": ["same_model_extraction"],
            },
        },
    ).as_dict()
    candidate["provenance"]["authoritative_contract_receipt"] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "topic_id": topic_id,
        "contract_id": f"rpg.world_forge.{topic_id}",
        "contract_version": "test-contract-v1",
        "canonical_contract_hash": "sha256:" + "b" * 64,
        "authored_draft_hash": "sha256:" + "c" * 64,
        "canonical_content_hash": canonical_candidate_content_hash(candidate),
        "materializer_version": "test-materializer-v1",
        "materialized": True,
    }
    unsigned = build_generation_artifact(
        candidate,
        run_id="run:review",
        job_id=f"job:{topic_id}",
        topic_id=topic_id,
        provider=candidate["provenance"],
        settings={"generator_version": "g1", "prompt_version": "p1"},
    )
    artifact = harden_and_sign_generation_artifact(candidate, unsigned)
    authored = attach_signed_llm_authorship(candidate, artifact)
    authored = bind_signed_authorship_policy(authored, {})
    provenance = dict(authored["provenance"])
    provenance["authoritative_contract_receipt"] = sign_record(
        candidate["provenance"]["authoritative_contract_receipt"]
    )
    authored["provenance"] = provenance
    return authored


def _run() -> dict:
    graph = CampaignTopicGraph(
        graph_version="test-v1",
        campaign_template="test",
        depth="quick",
        nodes=(
            CampaignTopicNode("rules", "Rules", "lore"),
            CampaignTopicNode("history", "History", "lore", dependencies=("rules",)),
        ),
    )
    settings = WorldTopicGenerationSettings(
        generator_version="g1",
        prompt_version="p1",
        provider_route="lmstudio",
        model="model",
        seed=1,
    )
    return {
        "run_id": "run:review",
        "world_id": "world:1",
        "draft_revision": 1,
        "status": "review",
        "graph": graph.as_dict(),
        "context": {
            "generation_context": {},
            "topic_directives": {},
            "entity_manifest_hash": "sha256:manifest",
            "target_topic_ids": ["rules", "history"],
        },
        "settings": settings.as_dict(),
        "plan": {},
        "progress": {
            "flagged_topic_ids": ["rules", "history"],
            "failed_topic_ids": [],
            "blocked_topic_ids": [],
        },
    }


def _result(topic_id: str, entity_id: str, name: str) -> dict:
    candidate = _candidate(topic_id, entity_id, name)
    return {
        "run_id": "run:review",
        "world_id": "world:1",
        "draft_revision": 1,
        "topic_id": topic_id,
        "status": "needs_review",
        "candidate": candidate,
        "candidate_hash": canonical_hash(candidate),
        "validation": {
            "status": "needs_review",
            "blocking": True,
            "reason_codes": ["same_model_extraction"],
            "issues": [],
        },
        "provider": {"model": "model"},
        "dependency_hashes": {},
        "dependency_trust": {},
        "job_id": f"job:{topic_id}",
    }


class _Cursor:
    rowcount = 1


class _GenerationRepository:
    def __init__(self) -> None:
        self.run = _run()
        self.results = {
            "rules": _result("rules", "ent:rules:001", "Night Curfew"),
            "history": _result("history", "ent:history:001", "The Long Blackout"),
        }
        self.updated: dict | None = None

    def get(self, context, run_id):
        del context, run_id
        return self.run

    def list_topic_results(self, context, *, run_id):
        del context, run_id
        return list(self.results.values())

    def update(self, context, **kwargs):
        del context
        self.updated = kwargs
        self.run = {**self.run, "plan": kwargs.get("plan", self.run["plan"])}
        return self.run


class _ScenarioRepository:
    def __init__(self) -> None:
        self.promotions: list[dict] = []

    def put_topic(self, context, **kwargs):
        del context
        self.promotions.append(kwargs)
        return kwargs


class _Connection:
    def __init__(self, generation: _GenerationRepository) -> None:
        self.generation = generation
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "UPDATE omnix_rpg_world_generation_topic_results" in sql:
            candidate = json.loads(params[0])
            candidate_hash = params[1]
            validation = json.loads(params[2])
            topic_id = params[5]
            row = self.generation.results[topic_id]
            row.update(
                {
                    "status": "accepted",
                    "candidate": candidate,
                    "candidate_hash": candidate_hash,
                    "validation": validation,
                }
            )
        return _Cursor()


class _Work:
    def __init__(self) -> None:
        self.world_generation = _GenerationRepository()
        self.world_scenarios = _ScenarioRepository()
        self.connection = _Connection(self.world_generation)
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        del args


def _install(monkeypatch: pytest.MonkeyPatch, work: _Work) -> None:
    context = type("Context", (), {"workspace_id": "workspace:1"})()
    monkeypatch.setattr(generation_acceptance, "bootstrap_local_tenant", lambda database: context)
    monkeypatch.setattr(generation_acceptance, "unit_of_work", lambda database: work)
    monkeypatch.setattr(
        generation_acceptance,
        "require_world_writable",
        lambda work_value, context_value, world_id: {"draft_revision": 1},
    )
    monkeypatch.setattr(
        generation_acceptance,
        "reconcile_world_generation",
        lambda run_id, database=None: work.world_generation.run,
    )


def test_accepting_edited_candidate_promotes_exact_review_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = _Work()
    _install(monkeypatch, work)
    original = work.world_generation.results["rules"]
    edited = dict(original["candidate"])
    edited["entities"] = [
        {
            **edited["entities"][0],
            "description": "Edited by the Game Master before acceptance.",
        }
    ]

    result = generation_acceptance.accept_world_generation_candidate(
        "run:review",
        "rules",
        candidate=edited,
        expected_candidate_hash=original["candidate_hash"],
    )

    assert result["accepted_topic_ids"] == ["rules"]
    assert work.committed is True
    assert len(work.world_scenarios.promotions) == 1
    promotion = work.world_scenarios.promotions[0]
    assert promotion["content"]["entities"][0]["description"].startswith("Edited")
    provenance = promotion["content"]["provenance"]
    assert provenance["generation_status"] == "accepted"
    assert provenance["authoring"]["approved_at"]
    assert provenance["review_acceptance"]["edited_before_acceptance"] is True
    assert work.world_generation.results["rules"]["status"] == "accepted"
    assert work.world_generation.updated["plan"]["review_decisions"]["rules"]["decision"] == "accept"


def test_accept_all_promotes_review_candidates_in_dependency_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = _Work()
    _install(monkeypatch, work)

    result = generation_acceptance.accept_world_generation_candidates("run:review")

    assert result["accepted_topic_ids"] == ["rules", "history"]
    assert [row["topic_id"] for row in work.world_scenarios.promotions] == [
        "rules",
        "history",
    ]
    assert all(row["status"] == "accepted" for row in work.world_generation.results.values())
    decisions = work.world_generation.updated["plan"]["review_decisions"]
    assert set(decisions) == {"rules", "history"}


def test_accept_rejects_stale_candidate_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    work = _Work()
    _install(monkeypatch, work)

    with pytest.raises(ValueError, match="world_generation_candidate_hash_conflict"):
        generation_acceptance.accept_world_generation_candidate(
            "run:review",
            "rules",
            expected_candidate_hash="sha256:stale",
        )

    assert work.world_scenarios.promotions == []
    assert work.rolled_back is True


def test_accept_rejects_candidate_without_reviewable_dossiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = _Work()
    _install(monkeypatch, work)
    original = work.world_generation.results["rules"]
    incomplete = dict(original["candidate"])
    incomplete["entities"] = [{
        **incomplete["entities"][0],
        "short_summary": "",
        "dossier": None,
    }]

    with pytest.raises(
        ValueError,
        match="world_generation_accept_dossiers_required:rules",
    ):
        generation_acceptance.accept_world_generation_candidate(
            "run:review",
            "rules",
            candidate=incomplete,
            expected_candidate_hash=original["candidate_hash"],
        )

    assert work.world_scenarios.promotions == []


def test_accept_allows_dossiers_with_repairable_blank_section_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = _Work()
    _install(monkeypatch, work)
    original = work.world_generation.results["rules"]
    candidate = dict(original["candidate"])
    entity = dict(candidate["entities"][0])
    dossier = dict(entity["dossier"])
    section = dict(dossier["sections"][0])
    section["title"] = ""
    dossier["sections"] = [section, *dossier["sections"][1:]]
    entity["dossier"] = dossier
    candidate["entities"] = [entity]

    result = generation_acceptance.accept_world_generation_candidate(
        "run:review",
        "rules",
        candidate=candidate,
        expected_candidate_hash=original["candidate_hash"],
    )

    assert result["accepted_topic_ids"] == ["rules"]
