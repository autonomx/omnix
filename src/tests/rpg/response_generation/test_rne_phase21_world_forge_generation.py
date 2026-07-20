from __future__ import annotations

from app.rpg.session.genesis.canon_audit import audit_generated_canon
from app.rpg.session.genesis.canon_relationships import compile_cross_domain_relationships
from app.rpg.session.genesis.compiler import compile_campaign_genesis
from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_pipeline import run_campaign_world_forge
from app.rpg.session.genesis.world_forge_default import (
    ReferenceSafeWorldForgeGenerator,
)
from app.rpg.session.genesis.world_forge_deterministic import (
    DeterministicWorldForgeGenerator,
)


def _contract() -> CampaignGenesisContract:
    return CampaignGenesisContract.model_validate(
        {
            "campaign_template": "summoned_heroes",
            "genre": "portal_fantasy",
            "tone": "fractured mythic fantasy",
            "world_options": {
                "starting_location": "vanta_gate",
                "difficulty": "normal",
                "world_activity": "living_world",
                "economy_pressure": "normal",
                "combat_lethality": "deadly",
                "seed": 7842,
            },
            "world_forge": {
                "depth": "standard",
                "background_expansion": False,
                "require_consistency_audit": True,
                "require_opening_dossiers": True,
            },
        }
    )


def test_parallel_world_forge_builds_rich_vexira_campaign_bible() -> None:
    contract = _contract()
    compiled = compile_campaign_genesis(contract)
    result = run_campaign_world_forge(
        contract,
        campaign_id="campaign:kavrix",
        compiled_genesis=compiled,
    )
    assert result.launch_ready is True, result.as_dict()
    assert len(result.generation.generation_order) > 2
    assert any(len(batch) > 1 for batch in result.generation.generation_order)
    bible = result.compilation.document
    vexira = bible["entities"]["npc:vexira_umbra"]
    assert "dark lacquered-bone skin" in vexira["appearance"]
    assert "Silent Chorus assassin" in vexira["backstory"]
    assert vexira["dossier_status"] == "complete"
    assert "npc:vexira_umbra" in bible["completeness"]["opening_actor_ids"]
    assert bible["discovery_state"]["entities"]["npc:vexira_umbra"] == "partially_known"
    assert bible["discovery_state"]["entities"]["location:vanta_gate"] == "partially_known"
    relationships = {row["kind"]: row for row in bible["relationships"] if row["source_id"] == "npc:vexira_umbra"}
    assert relationships["member_of"]["target_id"] == "faction:silent_chorus"
    assert relationships["present_at"]["target_id"] == "location:vanta_gate"
    assert bible["manifest"]["document_count"] >= 30
    assert bible["manifest"]["retrieval_card_count"] > bible["manifest"]["document_count"]
    assert bible["indexes"]["lexical"]["vexira"]
    assert bible["indexes"]["embedding_index"]["status"] == "not_built"
    assert bible["content_hash"].startswith("sha256:")


def test_launch_canon_resumes_into_full_revision_without_regeneration() -> None:
    contract = _contract()
    compiled = compile_campaign_genesis(contract)
    generator = ReferenceSafeWorldForgeGenerator(
        DeterministicWorldForgeGenerator()
    )
    launch = run_campaign_world_forge(
        contract,
        campaign_id="campaign:tiered",
        compiled_genesis=compiled,
        generator=generator,
        launch_only=True,
    )

    launch_ids = {topic.topic_id for topic in launch.generation.topics}
    assert launch.launch_ready is True
    assert launch_ids == {
        "realm",
        "regions",
        "factions",
        "current_conflicts",
        "hero_system",
        "locations",
        "npcs",
        "opening_threads",
    }
    assert launch.graph.metadata["generation_tier"] == "launch_canon"
    assert "history" in launch.graph.metadata["deferred_topic_ids"]

    expanded = run_campaign_world_forge(
        contract,
        campaign_id="campaign:tiered",
        compiled_genesis=compiled,
        generator=generator,
        existing_topics={topic.topic_id: topic for topic in launch.generation.topics},
        canon_revision=2,
    )

    expected_full_ids = {
        node.topic_id
        for node in expanded.graph.nodes
        if node.category not in {"compiler", "audit", "index", "bootstrap"}
    }
    assert expanded.launch_ready is True
    assert {topic.topic_id for topic in expanded.generation.topics} == expected_full_ids
    assert expanded.compilation.document["canon_revision"] == 2
    assert all(
        expanded.compilation.document["generation_provenance"][topic_id]
        == launch.compilation.document["generation_provenance"][topic_id]
        for topic_id in launch_ids
    )


def test_auditor_emits_structured_patches_for_dates_secrets_and_links() -> None:
    topic = GeneratedTopic(
        topic_id="broken",
        entities=(
            {
                "id": "npc:test",
                "name": "Test",
                "kind": "npc",
                "birth_year": 100,
                "current_year": 140,
                "age": 20,
                "visibility": "game_master_canon",
            },
        ),
        facts=(
            {
                "id": "secret:test:1",
                "content": "A private fact.",
                "visibility": "public",
                "known_by": ["npc:missing"],
            },
        ),
        relationships=(
            {
                "id": "relationship:test:missing",
                "source_id": "npc:test",
                "target_id": "faction:missing",
                "kind": "member_of",
                "visibility": "game_master_canon",
            },
        ),
    )
    audit = audit_generated_canon((topic,))
    assert audit.passed is False
    codes = {issue.code for issue in audit.issues}
    assert {"age_mismatch", "public_secret", "unknown_knower", "dangling_relationship_endpoint"}.issubset(codes)
    patches = [patch.as_dict() for patch in audit.patches]
    assert any(patch["field"] == "age" and patch["value"] == 40 for patch in patches)
    assert any(patch["field"] == "visibility" and patch["value"] == "npc_private" for patch in patches)
    assert any(patch["operation"] == "remove" and patch["collection"] == "relationships" for patch in patches)


def test_relationship_compiler_returns_only_dossier_derived_links() -> None:
    topic = GeneratedTopic(
        topic_id="npcs",
        entities=(
            {
                "id": "npc:vexira_umbra",
                "kind": "npc",
                "faction_ids": ["faction:silent_chorus"],
                "location_id": "location:vanta_gate",
            },
            {"id": "faction:silent_chorus", "kind": "faction"},
            {"id": "location:vanta_gate", "kind": "location"},
        ),
        relationships=(
            {
                "id": "relationship:explicit",
                "source_id": "faction:silent_chorus",
                "target_id": "location:vanta_gate",
                "kind": "controls",
            },
        ),
    )
    relationships = compile_cross_domain_relationships((topic,))
    kinds = {(row["source_id"], row["kind"], row["target_id"]) for row in relationships}
    assert ("npc:vexira_umbra", "member_of", "faction:silent_chorus") in kinds
    assert ("npc:vexira_umbra", "present_at", "location:vanta_gate") in kinds
    assert all(row["id"] != "relationship:explicit" for row in relationships)
