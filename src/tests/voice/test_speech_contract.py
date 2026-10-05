"""Voice, live voice and live speech share one speech contract (PA-3.3)."""
from __future__ import annotations

import ast
from pathlib import Path

from app.live_speech import stt, tts
from app.live_speech.stt_adapters import ParakeetServiceTranscriber
from app.live_speech.tts_adapters import QwenServiceSpeechSynthesizer
from app.runtime.feature_catalog import load_feature
from app.voice import contracts

APP = Path(__file__).resolve().parents[2] / "app"
SPEECH = {"voice": "voice", "live_voice": "live-voice", "live_speech": "live-speech"}


def test_live_speech_sessions_implement_the_speech_contract() -> None:
    assert stt.TranscriptUpdate is contracts.TranscriptUpdate
    assert tts.AudioDelta is contracts.AudioDelta
    assert issubclass(stt.BufferedStreamingTranscriber, contracts.StreamingTranscriber)
    assert issubclass(ParakeetServiceTranscriber, contracts.StreamingTranscriber)
    assert issubclass(tts.DeterministicSpeechSynthesizer, contracts.StreamingSpeechSynthesizer)
    assert issubclass(QwenServiceSpeechSynthesizer, contracts.StreamingSpeechSynthesizer)


def test_speech_modules_reach_each_other_and_chat_only_through_contracts() -> None:
    reached: set[str] = set()
    for package in SPEECH:
        for path in (APP / package).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
                    target = node.module.split(".")[1]
                    if target != package and (target in SPEECH or target == "chat"):
                        reached.add(node.module)

    assert reached <= {"app.voice.contracts", "app.chat.contracts"}
    assert load_feature("live-voice").uses == ("voice",)
    assert load_feature("live-speech").uses == ("voice",)
