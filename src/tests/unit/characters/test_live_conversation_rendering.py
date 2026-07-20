from pathlib import Path

from app.characters.live_conversation_rendering import (
    PronunciationCreateRequest,
    PronunciationStore,
    SpeechDeliveryPlanRequest,
    create_speech_delivery_plan,
)


def test_delivery_plan_is_bounded_and_contextual() -> None:
    reassurance = create_speech_delivery_plan(
        SpeechDeliveryPlanRequest(
            text="I'm sorry. Take your time.",
            stance="listen",
            emotional_attunement="expressive",
            response_length="detailed",
            response_onset_style="reflective",
            assistant_backchannel_mode="natural",
            serious=True,
        )
    )
    assert reassurance.speech_act == "reassurance"
    assert reassurance.energy == "low"
    assert reassurance.warmth == "high"
    assert reassurance.certainty == "moderate"
    assert reassurance.pace == "slightly_slow"
    assert reassurance.clause_pause == "long"
    assert reassurance.onset_policy.desired_perceived_onset_ms == 650
    assert reassurance.nonverbal_eligibility.sigh is True

    instruction = create_speech_delivery_plan(
        SpeechDeliveryPlanRequest(text="First, save the file.", stance="teach")
    )
    assert instruction.speech_act == "instruction"
    assert instruction.certainty == "high"


def test_delivery_plan_matches_browser_engaged_quick_uncertainty_policy() -> None:
    plan = create_speech_delivery_plan(
        SpeechDeliveryPlanRequest(
            text="Perhaps this might work.",
            stance="discuss",
            presence_preset="engaged",
            conversation_pace="quick",
            emotional_attunement="off",
            response_length="conversational",
            response_onset_style="immediate",
            assistant_backchannel_mode="off",
        )
    )

    assert plan.speech_act == "answer"
    assert plan.energy == "high"
    assert plan.warmth == "low"
    assert plan.certainty == "low"
    assert plan.pace == "slightly_fast"
    assert plan.clause_pause == "medium"
    assert plan.onset_policy.desired_perceived_onset_ms == 220
    assert plan.onset_policy.maximum_additional_delay_ms == 120
    assert plan.nonverbal_eligibility.breath is False
    assert plan.nonverbal_eligibility.acknowledgement is False
    assert plan.nonverbal_eligibility.amused_exhale is False


def test_delivery_plan_extracts_bounded_emphasis_like_browser_policy() -> None:
    plan = create_speech_delivery_plan(
        SpeechDeliveryPlanRequest(
            text="This is VERY IMPORTANT and MUST stay bounded.",
        )
    )

    assert plan.emphasis == ["VERY", "IMPORTANT", "MUST"]


def test_pronunciation_store_upserts_and_deletes_session_entries(tmp_path: Path) -> None:
    store = PronunciationStore(tmp_path / "pronunciations.json")
    created = store.create(
        "chat:one",
        PronunciationCreateRequest(phrase="Nika", pronunciation="NEE-kah"),
    )
    assert len(created.entries) == 1
    entry_id = created.entries[0].id

    updated = store.create(
        "chat:one",
        PronunciationCreateRequest(phrase="nika", pronunciation="NEE-kuh", locale="en-CA"),
    )
    assert len(updated.entries) == 1
    assert updated.entries[0].id == entry_id
    assert updated.entries[0].pronunciation == "NEE-kuh"

    reloaded = PronunciationStore(tmp_path / "pronunciations.json").list("chat:one")
    assert reloaded.entries == updated.entries

    removed = store.delete("chat:one", entry_id)
    assert removed.entries == []
