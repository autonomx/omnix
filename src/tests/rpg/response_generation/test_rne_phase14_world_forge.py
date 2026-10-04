from __future__ import annotations

from app.rpg.narrative_engine import (
    CampaignBibleSnapshot,
    WorldForgeProposal,
    apply_world_forge_proposal,
    audit_world_forge_proposal,
)


def _snapshot() -> CampaignBibleSnapshot:
    return CampaignBibleSnapshot(
        campaign_id="campaign:forge",
        revision=2,
        content_hash="sha256:existing",
        document={
            "entities": {
                "npc:bran": {"id": "npc:bran", "name": "Bran"},
                "location:rusty_flagon": {"id": "location:rusty_flagon", "name": "The Rusty Flagon"},
            },
            "facts": [
                {
                    "id": "fact:bran:occupation",
                    "content": "Bran keeps the Rusty Flagon.",
                    "authority": "objective_canon",
                    "entity_refs": ["npc:bran", "location:rusty_flagon"],
                }
            ],
        },
        provenance={},
        consistency_report={"passed": True},
        completeness={},
    )


def test_world_forge_rejects_contradictions_dangling_links_and_stale_revision() -> None:
    proposal = WorldForgeProposal(
        proposal_id="proposal:bad",
        campaign_id="campaign:forge",
        base_bible_revision=1,
        facts=(
            {
                "id": "fact:bran:occupation",
                "content": "Bran is the town blacksmith.",
                "authority": "generated_proposal",
                "entity_refs": ["npc:bran", "location:missing"],
            },
        ),
    )
    audit = audit_world_forge_proposal(_snapshot(), proposal)
    codes = {issue.code for issue in audit.issues}
    assert audit.passed is False
    assert {"stale_bible_revision", "contradiction", "dangling_entity_ref"}.issubset(codes)


def test_world_forge_approval_cross_links_and_promotes_generated_authority() -> None:
    proposal = WorldForgeProposal(
        proposal_id="proposal:good",
        campaign_id="campaign:forge",
        base_bible_revision=2,
        entities=(
            {"id": "location:east_road", "name": "East Road", "kind": "location"},
        ),
        facts=(
            {
                "id": "fact:east_road:condition",
                "content": "The East Road is muddy but passable.",
                "authority": "generated_proposal",
                "approved_authority": "objective_canon",
                "entity_refs": ["location:east_road"],
            },
        ),
        relationships=(
            {
                "id": "relationship:bran:east_road",
                "content": "Bran receives caravan reports from the East Road.",
                "authority": "generated_proposal",
                "entity_refs": ["npc:bran", "location:east_road"],
            },
        ),
        retrieval_cards=(
            {
                "id": "card:east_road",
                "summary": "A churned road leads east through wet fields.",
                "visibility": "player_known",
                "entity_refs": ["location:east_road"],
            },
        ),
        provenance={"generator": "world_forge_v1"},
    )
    document, audit = apply_world_forge_proposal(_snapshot(), proposal)
    assert audit.passed is True
    assert audit.cross_links["fact:east_road:condition"] == ("location:east_road",)
    assert "location:east_road" in document["entities"]
    added = next(row for row in document["facts"] if row["id"] == "fact:east_road:condition")
    assert added["authority"] == "objective_canon"
    assert added["approved_from_proposal"] == "proposal:good"
    assert document["generation_provenance"]["proposal:good"]["generator"] == "world_forge_v1"
