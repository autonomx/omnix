from app.gateway.tts_stream_contract import TtsStreamRequest, apply_pronunciation_lexicon


def test_pronunciation_lexicon_rewrites_synthesized_text_only() -> None:
    request = TtsStreamRequest.model_validate(
        {
            "text": "Nika visited New York with Nika.",
            "diagnostics_stream_id": "chat-live-pronunciation",
            "pronunciation_lexicon": [
                {"phrase": "Nika", "pronunciation": "NEE-kah", "locale": "en-US"},
                {"phrase": "New York", "pronunciation": "New Yawk", "locale": "en-US"},
            ],
            "delivery_plan": {"speech_act": "answer", "warmth": "moderate"},
        }
    )

    assert request.text == "NEE-kah visited New Yawk with NEE-kah."
    assert request.delivery_plan == {"speech_act": "answer", "warmth": "moderate"}
    assert request.parity_mode is False
    assert request.repetition_penalty >= 1.05


def test_pronunciation_longest_phrase_wins_and_is_bounded() -> None:
    result = apply_pronunciation_lexicon(
        "New York and York",
        [
            {"phrase": "York", "pronunciation": "YORK"},
            {"phrase": "New York", "pronunciation": "NEW-YORK"},
        ],
    )

    assert result == "NEW-YORK and YORK"
