from __future__ import annotations

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    DeterministicBeatPlanner,
    NarrativeSignificance,
    PresentationProfile,
    SceneChange,
    TurnPresentationRequest,
    bran_fixture_evidence,
    vexira_fixture_evidence,
)


def test_ordinary_dialogue_plans_reaction_then_direct_answer() -> None:
    request = TurnPresentationRequest(
        request_id="request:bran",
        turn_id="turn:bran",
        campaign_id="campaign:bran",
        player_input="How is the road today?",
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.IMMERSIVE,
        metadata={"response_mode": "dialogue"},
    )
    plan = DeterministicBeatPlanner().plan(request, bran_fixture_evidence())
    assert plan.profile is PresentationProfile.IMMERSIVE
    assert [beat.purpose for beat in plan.beats[:2]] == [
        BeatPurpose.PHYSICAL_REACTION,
        BeatPurpose.DIRECT_ANSWER,
    ]
    assert plan.beats[1].kind is BeatKind.DIALOGUE
    assert plan.beats[1].speaker_id == "npc:bran"


def test_major_vexira_dialogue_adapts_to_cinematic_escalation() -> None:
    request = TurnPresentationRequest(
        request_id="request:vexira",
        turn_id="turn:vexira",
        campaign_id="campaign:vexira",
        player_input="How dare you say I am not chosen?",
        actor_ids=("npc:vexira",),
        target_actor_id="npc:vexira",
        significance=NarrativeSignificance.MAJOR,
        presentation_profile=PresentationProfile.FAST,
        metadata={"response_mode": "dialogue"},
    )
    plan = DeterministicBeatPlanner().plan(request, vexira_fixture_evidence())
    assert plan.profile is PresentationProfile.CINEMATIC
    purposes = [beat.purpose for beat in plan.beats]
    assert purposes[:2] == [BeatPurpose.PHYSICAL_REACTION, BeatPurpose.DIRECT_ANSWER]
    assert BeatPurpose.LORE_REVEAL in purposes
    assert BeatPurpose.EMOTIONAL_ESCALATION in purposes
    assert BeatPurpose.ULTIMATUM in purposes
    assert [beat.sequence for beat in plan.beats] == list(range(1, len(plan.beats) + 1))


def test_scene_change_beats_precede_current_turn_dialogue() -> None:
    request = TurnPresentationRequest(
        request_id="request:arrival",
        turn_id="turn:arrival",
        campaign_id="campaign:arrival",
        player_input="Ask Bran where we are.",
        target_actor_id="npc:bran",
        scene_changes=(
            SceneChange(
                kind="location_changed",
                importance="major",
                evidence_refs=("location:rusty_flagon:atmosphere",),
            ),
        ),
        metadata={"response_mode": "dialogue"},
    )
    plan = DeterministicBeatPlanner().plan(request, bran_fixture_evidence())
    assert [beat.purpose for beat in plan.beats[:4]] == [
        BeatPurpose.SCENE_ESTABLISHMENT,
        BeatPurpose.ENVIRONMENTAL_CHANGE,
        BeatPurpose.PHYSICAL_REACTION,
        BeatPurpose.DIRECT_ANSWER,
    ]


def test_fast_routine_dialogue_remains_bounded() -> None:
    request = TurnPresentationRequest(
        request_id="request:fast",
        turn_id="turn:fast",
        campaign_id="campaign:fast",
        player_input="Hello.",
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.FAST,
        metadata={"response_mode": "dialogue"},
    )
    plan = DeterministicBeatPlanner().plan(request, bran_fixture_evidence())
    assert plan.word_budget == (25, 90)
    assert len(plan.beats) <= 3
    assert BeatPurpose.ULTIMATUM not in {beat.purpose for beat in plan.beats}
