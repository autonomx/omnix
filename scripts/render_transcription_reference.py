"""Render the reference conversation for the Phase 2 transcription check (run in the TTS environment).

Two voices (any two reference WAVs; the defaults are the AN4 speaker samples
that ship with TitaNet) speak a 12-line, ~60 s planning call through Qwen3 and
the Voice Studio assembler, plus one German line for the language check.
Reference turns are each line's speech onset and offset inside its assembled
span. Then run ``scripts/check_timed_transcription.py`` in the STT environment.

    python scripts/render_transcription_reference.py --out OUT [--voice-a A.wav --voice-b B.wav]
"""
import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

import app.providers.faster_qwen3_tts_provider as qwen_module  # noqa: E402
from app.platform.voice.assembly import AudioSpan, PausePolicy, assemble_chapter  # noqa: E402
from app.platform.voice.effects import read_mono, to_mono_pcm16  # noqa: E402

SAMPLES = ROOT / "resources/models/stt/speakerverification_en_titanet_large"
parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--voice-a", default=str(SAMPLES / "an255-fash-b.wav"))
parser.add_argument("--voice-b", default=str(SAMPLES / "cen7-fash-b.wav"))
args = parser.parse_args()
OUT = args.out
VOICES = {"ana": args.voice_a, "cen": args.voice_b}
qwen_module._clone_reference = lambda speaker: (VOICES.get(str(speaker), VOICES["ana"]), "")

CONVERSATION = [
    ("ana", "Good morning, and welcome to the weekly planning call."),
    ("cen", "Thanks for having me. I brought the numbers from last quarter."),
    ("ana", "Great. Let's start with the shipping delays, since those worried everyone."),
    ("cen", "The delays came from one supplier. We moved half the orders to a second warehouse in March."),
    ("ana", "Did that fix it?"),
    ("cen", "Mostly. Average delivery dropped from nine days to five."),
    ("ana", "That is a big improvement. What about the cost?"),
    ("cen", "Costs went up a little, about three percent, but customers complained far less."),
    ("ana", "I think that trade is worth it. Can you write that up for Friday?"),
    ("cen", "Sure, I will send a short summary with the charts by Thursday evening."),
    ("ana", "Perfect. One last thing: the new hire starts on Monday."),
    ("cen", "I will set up her accounts before then."),
]
GERMAN = ("Guten Morgen und willkommen zur wöchentlichen Planung. "
          "Die Lieferungen kommen jetzt schneller an, und die Kunden sind zufriedener.")


def render(provider, text: str, speaker: str, language: str) -> bytes:
    result = provider.generate_audio(text, speaker=speaker, language=language, parity_mode=True,
                                     non_streaming_mode=True, use_cuda_graphs=False)
    assert result.get("success") and not result.get("is_fallback"), result.get("error")
    return to_mono_pcm16(base64.b64decode(result.get("audio_base64") or result.get("audio")))


def speech_bounds(samples: np.ndarray, rate: int) -> tuple[float, float]:
    frame = int(rate * 0.01)
    count = len(samples) // frame
    energy = np.sqrt(np.mean(samples[: count * frame].reshape(count, frame) ** 2, axis=1) + 1e-12)
    loud = np.nonzero(20 * np.log10(energy) > 20 * np.log10(energy.max()) - 35)[0]
    return loud[0] * frame / rate, (loud[-1] + 1) * frame / rate


provider = qwen_module.FasterQwen3TTSProvider({"model_name": str(ROOT / "resources/models/tts/Qwen3-TTS-12Hz-0.6B-Base")})
print("start:", provider.start(), flush=True)
spans, bounds = [], []
for index, (speaker, text) in enumerate(CONVERSATION):
    wav = render(provider, text, speaker, "en")
    samples, rate = read_mono(wav)
    bounds.append(speech_bounds(samples, rate))
    spans.append(AudioSpan(f"s{index}", f"k{index}", speaker, text, wav, pause_before_ms=350 if index else None))
    print("line", index, speaker, round(len(samples) / rate, 2), flush=True)
assembled = assemble_chapter(spans, policy=PausePolicy())
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "conversation.wav").write_bytes(assembled.wav_bytes)
reference = []
for (speaker, text), entry, (onset, offset) in zip(CONVERSATION, assembled.timeline, bounds):
    reference.append({"speaker": speaker, "text": text, "start": round(entry.start_seconds + onset, 3),
                      "end": round(entry.start_seconds + offset, 3)})
(OUT / "conversation.json").write_text(json.dumps(reference, indent=2), encoding="utf-8")
german = render(provider, GERMAN, "cen", "de")
(OUT / "german.wav").write_bytes(german)
(OUT / "german.json").write_text(json.dumps({"language": "de", "text": GERMAN}), encoding="utf-8")
print("conversation seconds", round(assembled.timeline[-1].end_seconds, 2))
provider.stop()
