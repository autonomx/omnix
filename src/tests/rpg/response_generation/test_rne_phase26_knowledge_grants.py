from __future__ import annotations

from app.rpg.narrative_engine import (
    AuthorityClass,
    BeatPurpose,
    EvidenceBroker,
    EvidenceRecord,
    InMemoryEvidenceSource,
    NarrativeEngineService,
    TurnPresentationRequest,
    VisibilityClass,
    HermesResearchRequest,
    normalize_hermes_research,
    writer_payload,
)


def _evidence() -> tuple[EvidenceRecord, ...]:
    return (
        EvidenceRecord(
            evidence_id="public:road",
            content="The east road is muddy but passable.",
            authority=AuthorityClass.OBJECTIVE_CANON,
            visibility=VisibilityClass.PUBLIC,
            entity_refs=("npc:bran", "location:east_road"),
        ),
        EvidenceRecord(
            evidence_id="private:bran",
            content="Bran privately fears the missing caravan was attacked.",
            authority=AuthorityClass.NPC_BELIEF,
            visibility=VisibilityClass.NPC_PRIVATE,
            known_by=("npc:bran",),
            entity_refs=("npc:bran",),
        ),
        EvidenceRecord(
            evidence_id="private:vexira",
            content="Vexira knows the gate's hidden final name.",
            authority=AuthorityClass.SECRET_CANON,
            visibility=VisibilityClass.NPC_PRIVATE,
            known_by=("npc:vexira",),
            entity_refs=("npc:vexira",),
        ),
        EvidenceRecord(
            evidence_id="narrator:scar",
            content="A concealed scar tightens beneath Bran's sleeve.",
            authority=AuthorityClass.SECRET_CANON,
            visibility=VisibilityClass.NARRATOR_ONLY,
            entity_refs=("npc:bran",),
        ),
        EvidenceRecord(
            evidence_id="gm:true-name",
            content="The Unmaker's true name is reserved for the game master.",
            authority=AuthorityClass.SECRET_CANON,
            visibility=VisibilityClass.GAME_MASTER_ONLY,
        ),
    )


def _service() -> NarrativeEngineService:
    return NarrativeEngineService(
        evidence_broker=EvidenceBroker(
            [InMemoryEvidenceSource(_evidence(), source_id="phase26")]
        )
    )


def test_dialogue_and_narration_receive_distinct_preplanned_evidence_grants() -> None:
    request = TurnPresentationRequest(
        request_id="request:phase26:dialogue",
        turn_id="turn:phase26:dialogue",
        campaign_id="campaign:phase26",
        player_input="Bran, what happened to the caravan?",
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        metadata={"response_mode": "dialogue"},
    )
    result = _service().generate(request)
    speaker_ids = result.grants.allowed_ids("speaker", "npc:bran")
    narrator_ids = result.grants.allowed_ids("narrator")
    player_ids = result.grants.allowed_ids("player")

    assert "public:road" in speaker_ids
    assert "private:bran" in speaker_ids
    assert "narrator:scar" not in speaker_ids
    assert "private:vexira" not in speaker_ids
    assert "gm:true-name" not in speaker_ids

    assert "narrator:scar" in narrator_ids
    assert "private:bran" in narrator_ids
    assert "private:vexira" not in narrator_ids
    assert "gm:true-name" not in narrator_ids
    assert player_ids == frozenset({"public:road"})

    direct = next(
        beat for beat in result.plan.beats
        if beat.purpose is BeatPurpose.DIRECT_ANSWER
    )
    reaction = next(
        beat for beat in result.plan.beats
        if beat.purpose is BeatPurpose.PHYSICAL_REACTION
    )
    assert direct.metadata["evidence_scope"] == "speaker"
    assert set(direct.evidence_refs).issubset(speaker_ids)
    assert "narrator:scar" not in direct.evidence_refs
    assert reaction.metadata["evidence_scope"] == "narrator"
    assert set(reaction.evidence_refs).issubset(narrator_ids)

    payload = writer_payload(request, result.plan, result.retrieval.evidence)
    direct_rows = payload["evidence_by_beat"][direct.beat_id]
    assert "narrator:scar" not in {row["evidence_id"] for row in direct_rows}


def test_player_observation_cannot_plan_from_private_or_narrator_evidence() -> None:
    request = TurnPresentationRequest(
        request_id="request:phase26:observation",
        turn_id="turn:phase26:observation",
        campaign_id="campaign:phase26",
        player_input="I inspect Bran and the road.",
        actor_ids=("npc:bran",),
        metadata={"response_mode": "observation"},
    )
    result = _service().generate(request)
    answer = next(
        beat for beat in result.plan.beats
        if beat.purpose is BeatPurpose.DIRECT_ANSWER
    )
    assert answer.metadata["evidence_scope"] == "player"
    assert set(answer.evidence_refs).issubset(
        result.grants.allowed_ids("player")
    )
    assert "private:bran" not in answer.evidence_refs
    assert "narrator:scar" not in answer.evidence_refs


def test_hermes_findings_preserve_private_visibility_instead_of_laundering_it() -> None:
    request = HermesResearchRequest(
        research_id="research:phase26",
        campaign_id="campaign:phase26",
        query="What does Bran fear?",
    )
    result = normalize_hermes_research(
        request,
        {
            "sources": [
                {
                    "source_id": "source:bran",
                    "title": "Bran dossier",
                    "citation": "campaign-bible:bran",
                }
            ],
            "findings": [
                {
                    "finding_id": "finding:bran-fear",
                    "content": "Bran fears the caravan was attacked.",
                    "source_refs": ["source:bran"],
                    "authority": "npc_belief",
                    "visibility": "npc_private",
                    "known_by": ["npc:bran"],
                }
            ],
        },
    )
    evidence = result.evidence()[0]
    assert evidence.visibility is VisibilityClass.NPC_PRIVATE
    assert evidence.known_by == ("npc:bran",)
