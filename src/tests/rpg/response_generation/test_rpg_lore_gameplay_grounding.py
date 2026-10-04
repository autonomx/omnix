from __future__ import annotations

from app.rpg.narrative_engine import (
    AuthorityClass,
    CampaignBibleEvidenceSource,
    CampaignBibleSnapshot,
    DeterministicBeatPlanner,
    EvidenceBroker,
    EvidenceGrantSet,
    EvidenceQuery,
    EvidenceRecord,
    NarrativeEngineService,
    PresentationProfile,
    TurnPresentationRequest,
    VisibilityClass,
    campaign_bible_evidence,
)
from app.rpg.session.genesis import turn_grounding


def _snapshot() -> CampaignBibleSnapshot:
    return CampaignBibleSnapshot(
        campaign_id="campaign:rusty-flagon",
        revision=4,
        content_hash="sha256:rusty-flagon",
        document={
            "documents": [
                {
                    "document_id": "lore:location:rusty-flagon-tavern",
                    "topic_id": "locations",
                    "title": "Rusty Flagon Tavern",
                    "full_text": (
                        "The Rusty Flagon Tavern is a smoke-darkened roadside inn where "
                        "travelers exchange news beside a broad stone hearth. Bran keeps "
                        "the common room orderly and rents simple rooms upstairs."
                    ),
                    "summary_500": "A roadside inn, gathering place, and information crossroads.",
                    "keywords": ["Rusty Flagon", "tavern", "Bran"],
                    "entity_refs": ["location:rusty_flagon"],
                    "visibility": "public",
                },
                {
                    "document_id": "lore:location:hidden-cellar",
                    "topic_id": "locations",
                    "title": "Hidden Cellar",
                    "full_text": "A concealed cellar contains the innkeeper's private ledgers.",
                    "entity_refs": ["location:rusty_flagon"],
                    "visibility": "public",
                },
            ],
            "entities": {
                "location:rusty_flagon": {
                    "kind": "location",
                    "name": "Rusty Flagon Tavern",
                    "description": "A busy roadside tavern with a working hearth.",
                    "sensory_profile": "Hearth smoke, rain, and fresh bread.",
                    "services": ["rooms", "food", "drink"],
                    "secrets": ["The cellar hides private ledgers."],
                    "visibility": "public",
                }
            },
            "discovery_state": {
                "pages": {
                    "lore:location:rusty-flagon-tavern": "learned",
                    "lore:location:hidden-cellar": "hidden_from_player",
                },
                "entities": {
                    "location:rusty_flagon": "partially_known",
                },
            },
        },
        provenance={"source": "test"},
        consistency_report={},
        completeness={},
    )


def test_campaign_bible_projects_lore_pages_and_safe_dossiers_into_evidence() -> None:
    evidence = campaign_bible_evidence(_snapshot())
    by_id = {record.evidence_id: record for record in evidence}

    tavern = by_id["bible:document:lore:location:rusty-flagon-tavern"]
    assert "smoke-darkened roadside inn" in tavern.content
    assert tavern.visibility is VisibilityClass.PLAYER_KNOWN
    assert tavern.entity_refs == ("location:rusty_flagon",)

    hidden = by_id["bible:document:lore:location:hidden-cellar"]
    assert hidden.visibility is VisibilityClass.GAME_MASTER_ONLY

    dossier = by_id["bible:entity:location:rusty_flagon"]
    assert "hearth smoke" in dossier.content.casefold()
    assert "private ledgers" not in dossier.content


def test_lore_search_ranks_named_and_current_location_context_and_filters_hidden_pages() -> None:
    broker = EvidenceBroker([CampaignBibleEvidenceSource(_snapshot())])
    result = broker.retrieve(
        EvidenceQuery(
            text="What is this place? Tell me about the Rusty Flagon.",
            entity_ids=("location:rusty_flagon",),
            limit=4,
        )
    )

    assert result.evidence[0].metadata["title"] == "Rusty Flagon Tavern"
    assert "bible:document:lore:location:hidden-cellar" not in result.trace.selected_ids
    assert (
        "bible:document:lore:location:hidden-cellar",
        "game_master_only",
    ) in result.trace.excluded


def test_fast_dialogue_lore_question_overrides_runtime_only(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        turn_grounding,
        "load_campaign_bible_snapshot",
        lambda *args, **kwargs: snapshot,
    )
    monkeypatch.setattr(
        turn_grounding,
        "research_campaign_turn",
        lambda **kwargs: None,
    )

    packet = turn_grounding.build_turn_grounding_packet(
        {
            "ok": True,
            "scene": {"location_id": "location:rusty_flagon"},
            "resolved_result": {"response_mode": "dialogue"},
            "session": {"state": {}},
        },
        campaign_id=snapshot.campaign_id,
        player_input="Bran, what is the history of this tavern?",
        speaker_id="npc:bran",
        actor_ids=("npc:bran",),
        runtime_only=True,
    )

    assert packet.metadata["lore_search_required"] is True
    assert packet.metadata["runtime_only_overridden_for_lore"] is True
    assert packet.metadata["campaign_bible_evidence_count"] >= 3
    assert "location:rusty_flagon" in packet.metadata["grounding_entity_ids"]
    assert any("Rusty Flagon Tavern" in record.content for record in packet.evidence)


def test_dialogue_direct_answer_falls_back_to_query_ranked_lore() -> None:
    lore = EvidenceRecord(
        evidence_id="bible:document:rusty-flagon",
        content="Rusty Flagon Tavern is a roadside inn and information crossroads.",
        authority=AuthorityClass.OBJECTIVE_CANON,
        visibility=VisibilityClass.PUBLIC,
        entity_refs=("location:rusty_flagon",),
        source_revision=4,
    )
    grants = EvidenceGrantSet(
        player=(lore,),
        narrator=(lore,),
        speakers={"npc:bran": (lore,)},
    )
    request = TurnPresentationRequest(
        request_id="dialogue:campaign:turn:1",
        turn_id="turn:1",
        campaign_id="campaign:rusty-flagon",
        player_input="Bran, what is this tavern?",
        authoritative_outcome={"response_mode": "dialogue", "success": True},
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.FAST,
        metadata={
            "response_mode": "dialogue",
            "dialogue_speaker_ids": ["npc:bran"],
            "grounding_entity_ids": ["location:rusty_flagon"],
        },
    )

    plan = DeterministicBeatPlanner().plan(request, (lore,), grants=grants)
    direct_answer = next(beat for beat in plan.beats if beat.purpose.value == "direct_answer")
    assert direct_answer.evidence_refs == (lore.evidence_id,)
    assert "location:rusty_flagon" in NarrativeEngineService._entity_ids(request)
