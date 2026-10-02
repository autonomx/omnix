from __future__ import annotations

from typing import Any

from app.chat.store import _pop_ready_sentences
from app.live_voice.speech.tts_lane import PriorityTtsScheduler, TtsLanePriority
from tests.characterization.fakes import FakeTTS
from tests.characterization.harness import capture


class _FakeTtsProvider:
    provider_name = "characterization-fake-tts"

    def __init__(self, fake_tts: FakeTTS) -> None:
        self.fake_tts = fake_tts
        self.calls: list[dict[str, Any]] = []

    def generate_audio_stream(
        self,
        *,
        text: str,
        speaker: str | None,
        language: str,
        **kwargs: Any,
    ):
        self.calls.append(
            {
                "text": text,
                "speaker": speaker,
                "language": language,
                "kwargs": dict(kwargs),
            }
        )
        for frame_index, frame in enumerate(self.fake_tts.synthesize(text)):
            yield frame, 24_000, {"frame_index": frame_index}


def test_live_voice_tts_lane_matches_pre_refactor_golden() -> None:
    response = (
        "The first spoken phrase is ready. "
        "The second phrase follows clearly! "
        "A final thought closes the response"
    )
    fake_tts = FakeTTS(frame_count=2, frame_bytes=4)
    provider = _FakeTtsProvider(fake_tts)
    scheduler = PriorityTtsScheduler(log=lambda *_args, **_kwargs: None)

    def scenario() -> dict[str, Any]:
        complete_phrases, pending_tail = _pop_ready_sentences(response)
        phrases = [*complete_phrases]
        if pending_tail.strip():
            phrases.append(pending_tail.strip())

        scheduled = []
        for phrase_index, phrase in enumerate(phrases):
            frames = list(
                scheduler.stream(
                    provider,
                    text=phrase,
                    speaker="sofia-calm",
                    language="en-US",
                    kwargs={"chunk_size": 2, "temperature": 0.4},
                    priority=TtsLanePriority.ACCEPTED,
                )
            )
            scheduled.append(
                {
                    "phrase_index": phrase_index,
                    "text": phrase,
                    "frames": [
                        {
                            "pcm_hex": pcm.hex(),
                            "sample_rate": sample_rate,
                            "timing": timing,
                        }
                        for pcm, sample_rate, timing in frames
                    ],
                }
            )

        return {
            "input_text": response,
            "complete_phrases": complete_phrases,
            "pending_tail": pending_tail,
            "scheduled_phrases": scheduled,
            "provider_calls": provider.calls,
            "scheduler_after_turn": scheduler.snapshot(),
        }

    capture("live-voice-tts-lane", scenario)
