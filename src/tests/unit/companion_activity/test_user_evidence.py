from __future__ import annotations

from datetime import datetime, timezone

from app.companion_activity.user_evidence import user_activity_propositions

NOW = datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc)


def propositions(text: str, *, message_id: str = "msg:1"):
    return user_activity_propositions(
        session_id="chat:1",
        subject="activity:1",
        message_id=message_id,
        content=text,
        observed_at=NOW,
    )


def test_explicit_goal_is_user_authority_and_generation_neutral() -> None:
    values = propositions("I'm trying to beat the Iron Sentinel.")

    assert len(values) == 1
    value = values[0]
    assert value.predicate == "current_objective"
    assert value.value == "beat the Iron Sentinel"
    assert value.source_kind == "user"
    assert value.trust_level == "user_explicit"
    assert value.confidence == 1.0
    assert value.generation is None


def test_explicit_strategy_change_is_extracted_without_next_suffix() -> None:
    values = propositions("I'll try a bleed build next.")

    assert len(values) == 1
    assert values[0].predicate == "strategy"
    assert values[0].value == "a bleed build"


def test_bounded_commitment_creates_stable_open_loop() -> None:
    first = propositions("Three more tries, then I'm done.", message_id="msg:1")
    replay = propositions("Three more tries, then I'm done.", message_id="msg:1")

    assert len(first) == 1
    assert first[0].predicate == "open_loop"
    assert first[0].value["kind"] == "bounded_commitment"
    assert first[0].value["description"] == "Three more tries, then I'm done"
    assert first[0].value["loop_id"] == replay[0].value["loop_id"]
    assert first[0].proposition_id == replay[0].proposition_id


def test_explicit_blocker_is_supported() -> None:
    values = propositions("I'm stuck on the second phase.")

    assert len(values) == 1
    assert values[0].predicate == "blocker"
    assert values[0].value == {"description": "the second phase"}


def test_ordinary_conversation_does_not_create_activity_evidence() -> None:
    for text in (
        "That was interesting. What do you think?",
        "Can you explain how bleed builds work?",
        "I tried that yesterday.",
        "Maybe a bleed build would be good.",
        "How many more tries do people usually need?",
    ):
        assert propositions(text) == ()
