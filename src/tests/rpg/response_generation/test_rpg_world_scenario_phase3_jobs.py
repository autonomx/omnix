from __future__ import annotations

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.worlds.generation_coordinator import reusable_completed_topics
from app.rpg.worlds.generation_jobs import (
    WORLD_TOPIC_RESOURCE_CLASS,
    WorldTopicGenerationSettings,
    canonical_hash,
    plan_ready_topic_jobs,
    topic_generation_fingerprint,
)


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="test-world-graph-v1",
        campaign_template="classic_fantasy",
        depth="quick",
        nodes=(
            CampaignTopicNode(
                topic_id="realm",
                title="Realm",
                category="lore",
                generator_role="realm_architect",
            ),
            CampaignTopicNode(
                topic_id="regions",
                title="Regions",
                category="regions",
                dependencies=("realm",),
                generator_role="geography_architect",
            ),
        ),
    )


def _settings(**changes) -> WorldTopicGenerationSettings:
    values = {
        "generator_version": "generator-v1",
        "prompt_version": "prompt-v1",
        "provider_route": "lmstudio",
        "model": "qwen",
        "seed": 42,
    }
    values.update(changes)
    return WorldTopicGenerationSettings(**values)


def test_topic_fingerprint_covers_prompt_directives_dependencies_and_manifest() -> None:
    node = _graph().nodes[0]
    base, _, _ = topic_generation_fingerprint(
        node,
        normalized_topic_input={"genre": "fantasy"},
        dependency_hashes={},
        directives={"direction": "storm coast"},
        entity_manifest_hash="sha256:manifest-a",
        settings=_settings(),
    )
    prompt_changed, _, _ = topic_generation_fingerprint(
        node,
        normalized_topic_input={"genre": "fantasy"},
        dependency_hashes={},
        directives={"direction": "storm coast"},
        entity_manifest_hash="sha256:manifest-a",
        settings=_settings(prompt_version="prompt-v2"),
    )
    directive_changed, _, _ = topic_generation_fingerprint(
        node,
        normalized_topic_input={"genre": "fantasy"},
        dependency_hashes={},
        directives={"direction": "desert empire"},
        entity_manifest_hash="sha256:manifest-a",
        settings=_settings(),
    )
    manifest_changed, _, _ = topic_generation_fingerprint(
        node,
        normalized_topic_input={"genre": "fantasy"},
        dependency_hashes={},
        directives={"direction": "storm coast"},
        entity_manifest_hash="sha256:manifest-b",
        settings=_settings(),
    )

    assert len({base, prompt_changed, directive_changed, manifest_changed}) == 4


def test_only_dependency_ready_topics_receive_generic_jobs() -> None:
    graph = _graph()
    root_plans = plan_ready_topic_jobs(
        graph,
        run_id="run:1",
        world_id="world:one",
        draft_revision=1,
        generation_context={"genre": "fantasy"},
        topic_directives={},
        completed_topics={},
        existing_job_ids=(),
        entity_manifest_hash="sha256:manifest",
        settings=_settings(),
    )

    assert [plan.topic_id for plan in root_plans] == ["realm"]
    assert root_plans[0].job_payload["resource_class"] == WORLD_TOPIC_RESOURCE_CLASS
    assert root_plans[0].job_id.startswith("world-topic:world:one:draft:1:realm:")

    realm = {
        "status": "ready",
        "content_hash": "sha256:realm",
        "input_hash": root_plans[0].input_hash,
        "dependency_hashes": {},
        "provenance": {
            "generation_fingerprint": root_plans[0].fingerprint,
            "directive_hash": root_plans[0].directive_hash,
        },
    }
    reusable = reusable_completed_topics(
        graph,
        rows={"realm": realm},
        generation_context={"genre": "fantasy"},
        topic_directives={},
        entity_manifest_hash="sha256:manifest",
        settings=_settings(),
    )
    dependent_plans = plan_ready_topic_jobs(
        graph,
        run_id="run:1",
        world_id="world:one",
        draft_revision=1,
        generation_context={"genre": "fantasy"},
        topic_directives={},
        completed_topics=reusable,
        existing_job_ids=[root_plans[0].job_id],
        entity_manifest_hash="sha256:manifest",
        settings=_settings(),
    )

    assert [plan.topic_id for plan in dependent_plans] == ["regions"]
    assert dependent_plans[0].dependency_hashes == {"realm": "sha256:realm"}


def test_stale_completed_topic_is_not_reused_after_prompt_change() -> None:
    graph = _graph()
    plans = plan_ready_topic_jobs(
        graph,
        run_id="run:1",
        world_id="world:one",
        draft_revision=1,
        generation_context={"genre": "fantasy"},
        topic_directives={},
        completed_topics={},
        existing_job_ids=(),
        entity_manifest_hash="sha256:manifest",
        settings=_settings(),
    )
    old = plans[0]
    row = {
        "status": "ready",
        "content_hash": canonical_hash({"topic_id": "realm"}),
        "input_hash": old.input_hash,
        "dependency_hashes": {},
        "provenance": {
            "generation_fingerprint": old.fingerprint,
            "directive_hash": old.directive_hash,
        },
    }

    reusable = reusable_completed_topics(
        graph,
        rows={"realm": row},
        generation_context={"genre": "fantasy"},
        topic_directives={},
        entity_manifest_hash="sha256:manifest",
        settings=_settings(prompt_version="prompt-v2"),
    )

    assert reusable == {}
