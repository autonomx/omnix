from __future__ import annotations

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.worlds.generation_jobs import (
    WorldTopicGenerationSettings,
    plan_ready_topic_jobs,
)


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="manifest-job-contract-v1",
        campaign_template="classic_fantasy",
        depth="quick",
        nodes=(
            CampaignTopicNode(
                topic_id="realm",
                title="Realm",
                category="lore",
                target_count=1,
            ),
            CampaignTopicNode(
                topic_id="actors",
                title="Actors",
                category="actors",
                target_count=2,
            ),
        ),
    )


def _settings() -> WorldTopicGenerationSettings:
    return WorldTopicGenerationSettings(
        generator_version="generator-v1",
        prompt_version="prompt-v1",
        provider_route="lmstudio",
        model="qwen",
        seed=42,
    )


def test_every_ready_job_carries_one_shared_authoritative_manifest() -> None:
    plans = plan_ready_topic_jobs(
        _graph(),
        run_id="run:manifest",
        world_id="world:manifest",
        draft_revision=1,
        generation_context={"genre": "fantasy"},
        topic_directives={},
        completed_topics={},
        existing_job_ids=(),
        entity_manifest_hash="sha256:request-manifest",
        settings=_settings(),
    )

    assert {plan.topic_id for plan in plans} == {"actors", "realm"}
    payloads = [dict(plan.job_payload["input_payload"]) for plan in plans]
    manifest_hashes = {str(payload["entity_manifest_hash"]) for payload in payloads}
    manifests = [dict(payload["entity_manifest"]) for payload in payloads]

    assert len(manifest_hashes) == 1
    assert all(manifest["content_hash"] in manifest_hashes for manifest in manifests)
    assert manifests[0] == manifests[1]
    assert all(
        payload["requested_entity_manifest_hash"] == "sha256:request-manifest"
        for payload in payloads
    )

    slots_by_topic = {
        plan.topic_id: list(plan.job_payload["input_payload"]["entity_manifest_slots"])
        for plan in plans
    }
    assert [row["entity_id"] for row in slots_by_topic["actors"]] == [
        "ent:actors:001",
        "ent:actors:002",
    ]
    assert [row["entity_id"] for row in slots_by_topic["realm"]] == [
        "ent:realm:001"
    ]
    assert all(
        row["topic_id"] == topic_id
        for topic_id, slots in slots_by_topic.items()
        for row in slots
    )

    metadata_by_topic = {
        plan.topic_id: dict(plan.job_payload["metadata"])
        for plan in plans
    }
    assert metadata_by_topic["actors"]["entity_manifest_slot_count"] == 2
    assert metadata_by_topic["realm"]["entity_manifest_slot_count"] == 1
    assert {
        metadata["entity_manifest_hash"]
        for metadata in metadata_by_topic.values()
    } == manifest_hashes
