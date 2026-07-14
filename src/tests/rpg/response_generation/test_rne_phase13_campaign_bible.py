from __future__ import annotations

from app.rpg.narrative_engine import (
    AuthorityClass,
    CampaignBibleEvidenceSource,
    CampaignBibleSnapshot,
    EvidenceAccessContext,
    EvidenceBroker,
    EvidenceQuery,
)


def _snapshot() -> CampaignBibleSnapshot:
    return CampaignBibleSnapshot(
        campaign_id="campaign:phase13",
        revision=4,
        content_hash="sha256:test",
        document={
            "facts": [
                {
                    "id": "fact:bran:public",
                    "content": "Bran keeps the Rusty Flagon.",
                    "authority": "objective_canon",
                    "visibility": "public",
                    "entity_refs": ["npc:bran", "location:rusty_flagon"],
                },
                {
                    "id": "fact:bran:private",
                    "content": "Bran is worried about the missing caravan.",
                    "authority": "npc_belief",
                    "visibility": "npc_private",
                    "known_by": ["npc:bran"],
                    "entity_refs": ["npc:bran"],
                },
            ],
            "retrieval_cards": [
                {
                    "id": "card:flagon:rain",
                    "summary": "Rain drums against the tavern shutters.",
                    "authority": "scene_observation",
                    "visibility": "player_known",
                    "entity_refs": ["location:rusty_flagon"],
                }
            ],
        },
        provenance={"source": "world_forge"},
        consistency_report={"passed": True},
        completeness={"score": 0.75},
    )


def test_campaign_bible_records_keep_revision_authority_and_visibility() -> None:
    broker = EvidenceBroker([CampaignBibleEvidenceSource(_snapshot())])
    player_result = broker.retrieve(
        EvidenceQuery(
            text="Bran at the tavern",
            entity_ids=("npc:bran",),
            access=EvidenceAccessContext(player_id="player"),
        )
    )
    assert "fact:bran:public" in player_result.trace.selected_ids
    assert "fact:bran:private" not in player_result.trace.selected_ids
    assert ("fact:bran:private", "npc_private") in player_result.trace.excluded
    public = next(row for row in player_result.evidence if row.evidence_id == "fact:bran:public")
    assert public.authority is AuthorityClass.OBJECTIVE_CANON
    assert public.source_revision == 4
    assert public.metadata["campaign_bible_hash"] == "sha256:test"

    bran_result = broker.retrieve(
        EvidenceQuery(
            text="missing caravan",
            entity_ids=("npc:bran",),
            access=EvidenceAccessContext(player_id="player", speaker_id="npc:bran"),
        )
    )
    assert "fact:bran:private" in bran_result.trace.selected_ids
