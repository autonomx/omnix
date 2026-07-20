#!/usr/bin/env python3
"""Generate cached voice-matched live cue WAV packs with the active TTS provider.

By default this generates the spoken acknowledgement cues (``mhm`` and ``hmm``).
Nonverbal inhale/exhale prompts are opt-in because provider quality varies and each
voice pack should be auditioned before those files are shipped.
"""
from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.gateway.tts_stream_contract import audio_chunk_to_pcm16_bytes  # noqa: E402
from app.runtime_paths import resources_data_root  # noqa: E402
from app.shared import get_tts_provider  # noqa: E402

DEFAULT_PROMPTS = {
    "mhm": "Mhm.",
    "hmm": "Hmm.",
}
EXPERIMENTAL_NONVERBAL_PROMPTS = {
    "inhale": "[soft inhale]",
    "amused_exhale": "[quiet amused exhale]",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", action="append", required=True, help="Voice clone ID; repeat for multiple voices.")
    parser.add_argument("--variants", type=int, default=4, choices=range(1, 9))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=resources_data_root() / "voice_cues",
        help="Cue-pack root served by /api/voice/cues.",
    )
    parser.add_argument("--language", default="English")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--include-experimental-nonverbal",
        action="store_true",
        help="Also generate inhale and amused-exhale prompts; audition before production use.",
    )
    parser.add_argument(
        "--prompt",
        action="append",
        default=[],
        metavar="CUE=TEXT",
        help="Override or add one supported cue prompt.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prompts = dict(DEFAULT_PROMPTS)
    if args.include_experimental_nonverbal:
        prompts.update(EXPERIMENTAL_NONVERBAL_PROMPTS)
    for raw in args.prompt:
        cue_id, separator, text = raw.partition("=")
        if not separator or cue_id not in {"mhm", "hmm", "inhale", "amused_exhale"} or not text.strip():
            raise SystemExit(f"Invalid --prompt value: {raw!r}")
        prompts[cue_id] = text.strip()

    provider = get_tts_provider()
    if provider is None or not hasattr(provider, "generate_audio_stream"):
        raise SystemExit("The active TTS provider does not support streaming generation.")

    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for voice_id in args.voice:
        voice_id = voice_id.strip()
        if not voice_id or any(character in voice_id for character in "/\\") or voice_id in {".", ".."}:
            raise SystemExit(f"Invalid voice ID: {voice_id!r}")
        voice_dir = args.output_root / voice_id
        voice_dir.mkdir(parents=True, exist_ok=True)
        for cue_id, prompt in prompts.items():
            for variant in range(1, args.variants + 1):
                variant_id = f"{cue_id}-v{variant}"
                output = voice_dir / f"{variant_id}.wav"
                if output.exists() and not args.overwrite:
                    skipped.append({"voice_id": voice_id, "variant_id": variant_id, "reason": "exists"})
                    continue
                pcm_bytes, sample_rate = synthesize(
                    provider,
                    voice_id=voice_id,
                    text=prompt,
                    language=args.language,
                    variant=variant,
                )
                write_wav(output, pcm_bytes, sample_rate)
                generated.append(
                    {
                        "voice_id": voice_id,
                        "cue_id": cue_id,
                        "variant_id": variant_id,
                        "path": str(output),
                        "sample_rate": sample_rate,
                        "samples": len(pcm_bytes) // 2,
                        "experimental_nonverbal": cue_id in EXPERIMENTAL_NONVERBAL_PROMPTS,
                    }
                )

    print(json.dumps({"generated": generated, "skipped": skipped}, indent=2))
    return 0


def synthesize(
    provider: Any,
    *,
    voice_id: str,
    text: str,
    language: str,
    variant: int,
) -> tuple[bytes, int]:
    chunks: list[bytes] = []
    sample_rate = 0
    stream = provider.generate_audio_stream(
        text=text,
        speaker=voice_id,
        language=language,
        chunk_size=8,
        temperature=min(0.85, 0.56 + variant * 0.04),
        top_k=20,
        top_p=0.85,
        repetition_penalty=1.05,
        append_silence=False,
        non_streaming_mode=False,
        parity_mode=False,
        max_new_tokens=64,
    )
    for audio_chunk, resolved_rate, _timing in stream:
        pcm = audio_chunk_to_pcm16_bytes(audio_chunk)
        if not pcm:
            continue
        rate = int(resolved_rate or 24_000)
        if sample_rate and rate != sample_rate:
            raise RuntimeError(f"Provider changed sample rate within one cue: {sample_rate} -> {rate}")
        sample_rate = rate
        chunks.append(pcm[: len(pcm) - (len(pcm) % 2)])
    payload = b"".join(chunks)
    if not payload:
        raise RuntimeError(f"TTS provider returned no audio for {voice_id!r}: {text!r}")
    return payload, sample_rate or 24_000


def write_wav(path: Path, pcm_bytes: bytes, sample_rate: int) -> None:
    temporary = path.with_suffix(".wav.tmp")
    with wave.open(str(temporary), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm_bytes)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
