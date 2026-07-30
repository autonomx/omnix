from __future__ import annotations

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds.generation_coordinator import available_completed_topics
from app.rpg.worlds.generation_retry import _previous_result_rows
from app.rpg.worlds.generation_jobs import (
    WorldTopicGenerationSettings,
    canonical_hash,
    plan_ready_topic_jobs,
)


def test_manual_field_retry_preserves_unselected_entities_and_fields() -> None:
    prior = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Ada",
                "motivation": "Protect the relay workers.",
                "next_action": "Wait.",
            },
            {
                "id": "actor:bram",
                "kind": "actor",
                "name": "Bram",
                "motivation": "Control the harbor cranes.",
                "next_action": "Inspect the eastern crane.",
            },
        ),
    )
    generated = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Changed Ada",
                "motivation": "Changed motivation.",
                "next_action": "Inspect the flooded relay chamber.",
            },
            {
                "id": "actor:bram",
                "kind": "actor",
                "name": "Changed Bram",
                "motivation": "Abandon the harbor.",
                "next_action": "Leave immediately.",
            },
        ),
    )

    scoped = ReferenceSafeWorldForgeGenerator._manual_retry_candidate(
        generated,
        {
            "topic_directives": {
                "manual_retry": {
                    "prior_candidate": prior.as_dict(),
                    "scope": "entity_fields",
                    "entity_ids": ["actor:ada"],
                    "fields": ["next_action"],
                    "reason_codes": ["weak_operational_state"],
                    "instructions": ["Replace the placeholder with a concrete action."],
                }
            }
        },
    )

    assert scoped.entities[0]["name"] == "Ada"
    assert scoped.entities[0]["motivation"] == "Protect the relay workers."
    assert scoped.entities[0]["next_action"] == "Inspect the flooded relay chamber."
    assert scoped.entities[1] == prior.entities[1]
    assert scoped.provenance["targeted_regeneration_updated_fields"] == ["next_action"]


def test_retry_of_a_failed_topic_without_prior_canon_needs_no_keep_replace_decision() -> None:
    node = CampaignTopicNode("groups", "Organisations and Institutions", "lore")
    generated = GeneratedTopic(
        topic_id="groups",
        entities=(
            {
                "id": "ent:groups:001",
                "kind": "group",
                "name": "OmniCorp Directorate",
            },
        ),
    )

    result = ReferenceSafeWorldForgeGenerator._mark_manual_decision_required(
        node,
        generated,
        {
            "topic_directives": {
                "manual_retry": {
                    "parent_run_id": "run:failed",
                    "prior_status": "failed",
                    "prior_candidate": None,
                }
            }
        },
    )

    assert result is generated
    assert "generation_review" not in result.provenance


def test_valid_pending_review_candidate_feeds_downstream_generation() -> None:
    graph = CampaignTopicGraph(
        graph_version="test-v1",
        campaign_template="test",
        depth="quick",
        nodes=(
            CampaignTopicNode("rules", "Rules", "lore"),
            CampaignTopicNode(
                "history",
                "History",
                "lore",
                dependencies=("rules",),
            ),
        ),
    )
    candidate = GeneratedTopic(
        topic_id="rules",
        entities=({"id": "ent:rules:001", "kind": "rule", "name": "The Rule"},),
    ).as_dict()
    settings = WorldTopicGenerationSettings(
        generator_version="world-generator-v1",
        prompt_version="world-prompt-v1",
        provider_route="lmstudio",
        model="model",
        seed=1,
    )
    available, _, _ = available_completed_topics(
        graph,
        rows={},
        generation_context={},
        topic_directives={},
        entity_manifest_hash="sha256:manifest",
        settings=settings,
        current_run_id="run:retry",
        run_results={
            "rules": {
                "run_id": "run:retry",
                "topic_id": "rules",
                "status": "needs_review",
                "candidate": candidate,
                "candidate_hash": canonical_hash(candidate),
                "validation": {
                    "reason_codes": ["manual_retry_decision_required"],
                },
                "dependency_hashes": {},
            }
        },
    )

    plans = plan_ready_topic_jobs(
        graph,
        run_id="run:retry",
        world_id="world:test",
        draft_revision=1,
        generation_context={},
        topic_directives={},
        completed_topics=available,
        existing_job_ids=("job:rules",),
        entity_manifest_hash="sha256:manifest",
        settings=settings,
    )

    assert available["rules"]["dependency_trust"] == "quarantined"
    assert [plan.topic_id for plan in plans] == ["history"]
    assert plans[0].job_payload["input_payload"]["dependency_trust"] == {
        "rules": "quarantined"
    }


def test_manual_retry_pins_unselected_ready_dependency() -> None:
    graph = CampaignTopicGraph(
        graph_version="test-v1",
        campaign_template="test",
        depth="quick",
        nodes=(
            CampaignTopicNode("rules", "Rules", "lore"),
            CampaignTopicNode(
                "history",
                "History",
                "lore",
                dependencies=("rules",),
            ),
        ),
    )
    candidate = GeneratedTopic(
        topic_id="rules",
        entities=({"id": "ent:rules:001", "kind": "rule", "name": "The Rule"},),
    ).as_dict()
    settings = WorldTopicGenerationSettings(
        generator_version="world-generator-v1",
        prompt_version="world-prompt-v1",
        provider_route="lmstudio",
        model="model",
        seed=1,
    )

    available, reusable, protected = available_completed_topics(
        graph,
        rows={
            "rules": {
                "topic_id": "rules",
                "status": "ready",
                "source": "ai",
                "content": candidate,
                "content_hash": canonical_hash(candidate),
                "input_hash": "old-input",
                "dependency_hashes": {},
                "provenance": {
                    "generation_fingerprint": "old-fingerprint",
                    "directive_hash": "old-directive",
                    "review_acceptance": {"run_id": "run:parent"},
                },
            }
        },
        generation_context={"changed": True},
        topic_directives={},
        entity_manifest_hash="sha256:new-manifest",
        settings=settings,
        forced_topic_ids=("history",),
        pinned_topic_ids=("rules",),
        current_run_id="run:retry",
    )

    assert available["rules"]["content"] == candidate
    assert reusable == ()
    assert protected == ("rules",)


def test_authoring_canon_overrides_stale_failed_result_for_retry_fallback() -> None:
    candidate = GeneratedTopic(
        topic_id="rules",
        entities=({"id": "ent:rules:001", "kind": "rule", "name": "The Rule"},),
    ).as_dict()

    previous = _previous_result_rows(
        [
            {
                "topic_id": "rules",
                "status": "failed",
                "candidate": None,
                "candidate_hash": "",
                "validation": {"reason_codes": ["provider_failed"]},
            }
        ],
        [
            {
                "topic_id": "rules",
                "status": "ready",
                "content": candidate,
                "content_hash": canonical_hash(candidate),
                "provenance": {
                    "generation_status": "accepted",
                    "review_acceptance": {"run_id": "run:parent"},
                },
            }
        ],
    )

    assert previous["rules"]["status"] == "accepted"
    assert previous["rules"]["candidate"] == candidate


def test_accepted_ancestor_candidate_fills_failed_retry_result() -> None:
    candidate = GeneratedTopic(
        topic_id="groups",
        entities=({"id": "ent:groups:001", "kind": "group", "name": "The Group"},),
    ).as_dict()

    previous = _previous_result_rows(
        [
            {
                "topic_id": "groups",
                "status": "failed",
                "candidate": None,
                "candidate_hash": "",
            }
        ],
        [],
        [
            {
                "topic_id": "groups",
                "status": "accepted",
                "candidate": candidate,
                "candidate_hash": canonical_hash(candidate),
            }
        ],
    )

    assert previous["groups"]["status"] == "accepted"
    assert previous["groups"]["candidate"] == candidate
