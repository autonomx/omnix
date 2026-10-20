"""Score timed, diarized transcription against the Phase 2 reference (run in the STT environment).

Reads the clips written by ``scripts/render_transcription_reference.py`` and
prints the Phase 2 exit measures: diarization error rate (< 15%), median
word-boundary error (< 80 ms), WER, the SRT lint, and the German clip's
language and WER. Needs Parakeet-TDT and TitaNet installed (Speech models).

    python scripts/check_timed_transcription.py --ref OUT
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

from app.platform.voice.transcripts import (  # noqa: E402
    TranscriptDocument, diarization_error_rate, export_transcript, lint_subtitles, subtitle_cues, word_error_rate,
)
from services.stt import timed_transcription as timed  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--ref", type=Path, required=True)
REF = parser.parse_args().ref


def load(path: Path) -> np.ndarray:
    samples, rate = sf.read(str(path), dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if rate != 16_000:
        divisor = np.gcd(rate, 16_000)
        samples = resample_poly(samples, 16_000 // divisor, rate // divisor).astype(np.float32)
    return samples


reference = json.loads((REF / "conversation.json").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as work:
    started = time.perf_counter()
    document = timed.transcribe_timed(load(REF / "conversation.wav"), language="en", diarize=True, workdir=Path(work))
    print(f"conversation transcribed in {time.perf_counter() - started:.1f}s; diarized={document['diarized']}")
doc = TranscriptDocument.model_validate(document)
words = [word for segment in document["segments"] for word in segment["words"]]
ref_turns = [(entry["start"], entry["end"], entry["speaker"]) for entry in reference]
hyp_turns = [(segment["start"], segment["end"], segment["speaker"]) for segment in document["segments"]]
der = diarization_error_rate(ref_turns, hyp_turns)
boundary = timed.word_boundary_error([(entry["start"], entry["end"]) for entry in reference], words)
wer = word_error_rate(" ".join(entry["text"] for entry in reference), doc.text)
print("speakers:", document["speakers"], "segments:", len(document["segments"]))
for segment in document["segments"]:
    print(f"  {segment['start']:6.2f}-{segment['end']:6.2f} {segment['speaker']}: {segment['text']}")
print(f"DER {der:.3f} (exit < 0.15)")
print(f"median word-boundary error {boundary * 1000:.0f} ms (exit < 80 ms)")
print(f"WER {wer:.3f}")
srt, _ = export_transcript(doc, "srt")
(REF / "conversation.srt").write_text(srt, encoding="utf-8")
print("SRT lint problems:", lint_subtitles(subtitle_cues(doc.normalized())))

german = json.loads((REF / "german.json").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as work:
    german_doc = timed.transcribe_timed(load(REF / "german.wav"), language="de", diarize=True, workdir=Path(work))
print("German:", german_doc["language"], "|", german_doc["text"])
print(f"German WER {word_error_rate(german['text'], german_doc['text']):.3f}; speakers {german_doc['speakers']}")
print("loaded:", timed.ASR.loaded, timed.SPEAKERS.loaded)
