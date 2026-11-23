"""A call name recognition spelled as an everyday word is written as the name (owner report, 2026-11-21)."""

from __future__ import annotations

from app.conversation.heard_names import called_by, repair_heard_names


def test_a_name_heard_as_another_spelling_is_written_as_the_name() -> None:
    call = ["Jinx", "Ehsan Matean"]
    # The call of 2026-11-21: "Jinx" was heard as "Jenks", though the decoder boosted it.
    assert repair_heard_names("Hey Jenks, how are you?", call) == "Hey Jinx, how are you?"
    assert repair_heard_names("Jenks, what do you see?", call) == "Jinx, what do you see?"
    assert repair_heard_names("What do you think, Jenks?", call) == "What do you think, Jinx?"
    assert repair_heard_names("I told Jenks about it", call) == "I told Jinx about it"
    assert repair_heard_names("That was Jenks's idea", call) == "That was Jinx's idea"
    assert repair_heard_names("hey jinx, you there", call) == "hey Jinx, you there"
    assert repair_heard_names("This is Ehsen.", call) == "This is Ehsan."  # a full name is called by its first
    # Several at once, and the rest of the words as they were heard.
    assert repair_heard_names("Jenks, tell Ehsen   the plan.", call) == "Jinx, tell Ehsan   the plan."


def test_words_that_are_not_said_as_the_name_stay_as_heard() -> None:
    call = ["Jinx", "Luke", "Afra"]
    for heard in ("Don't jinx it.", "I like that idea", "I went to Africa", "Jinx is here", "", "how was your day?"):
        assert repair_heard_names(heard, call) == heard, heard
    # A word that sounds like two of the names is neither.
    assert repair_heard_names("Aphra, hi", ["Afra", "Afro"]) == "Aphra, hi"
    # A name too short to match by sound is never written over ("be" beside Bea).
    assert repair_heard_names("Bee, hi", ["Bea"]) == "Bee, hi"
    assert repair_heard_names("Hey Jenks", []) == "Hey Jenks"


def test_everyday_words_answers_and_numbers_are_not_heard_as_names() -> None:
    # Review 2026-11-22: each of these was written over as a call member's name.
    for heard, call in (
        ("So there's a problem.", ["Terry"]),  # a contraction, not a possessive
        ("Well there's that.", ["Terry"]),
        ("Nine?", ["Nina"]),  # a one-word answer
        ("Uh, nine?", ["Nina"]),
        ("salt and pepper?", ["Piper"]),  # "and" does not set off an address
        ("Where?", ["Wera"]),
    ):
        assert repair_heard_names(heard, call) == heard, heard
    # A possessive is still a name, in or out of a sentence's start.
    assert repair_heard_names("Jenks's turn now", ["Jinx"]) == "Jinx's turn now"


def test_a_text_still_being_heard_does_not_end_in_an_address() -> None:
    # A partial's last word may go on ("there" → "therefore", "jenks" → "jenkins"); the final is repaired.
    assert repair_heard_names("Wait, there", ["Terry"], complete=False) == "Wait, there"
    assert repair_heard_names("hey jenks", ["Jinx"], complete=False) == "hey jenks"
    assert repair_heard_names("hey jenks", ["Jinx"]) == "hey Jinx"
    # Set off inside the partial, or written as a name: already an address.
    assert repair_heard_names("Jenks, what", ["Jinx"], complete=False) == "Jinx, what"
    assert repair_heard_names("I told Jenks", ["Jinx"], complete=False) == "I told Jinx"


def test_the_names_a_call_is_called_by() -> None:
    assert called_by(["Jinx", "Dr Abhishek Kumar", "Ehsan Matean", "Jinx", "Al B", "Dr"]) == [
        "Jinx", "Abhishek", "Ehsan", "Dr"]
