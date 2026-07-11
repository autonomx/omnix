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
            serious=True,
        )
    )
    assert reassurance.speech_act == "reassurance"
    assert reassurance.energy == "low"
    assert reassurance.warmth == "high"
    assert reassurance.pace == "slightly_slow"
    assert reassurance.clause_pause == "long"

    instruction = create_speech_delivery_plan(
        SpeechDeliveryPlanRequest(text="First, save the file.", stance="teach")
    )
    assert instruction.speech_act == "instruction"
    assert instruction.certainty == "high"


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
