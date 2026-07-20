#!/usr/bin/env python3
"""Generate cached voice-matched live cue WAV packs.

By default the generator calls the already-running Omnix TTS service. Use
``--in-process`` only when the current Python environment can load the TTS
runtime itself.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_TTS_SERVER_URL = "http://127.0.0.1:5101"

DEFAULT_PROMPTS = {
    "mhm": "Mhm.",
    "hmm": "Hmm.",
}
EXPERIMENTAL_NONVERBAL_PROMPTS = {
    "inhale": "[soft inhale]",
    "amused_exhale": "[quiet amused exhale]",
}


def default_output_root() -> Path:
    override = str(os.environ.get("OMNIX_LIVE_VOICE_CUE_ROOT") or "").strip()
    return Path(override) if override else REPO_ROOT / "resources" / "data" / "voice_cues"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", action="append", required=True, help="Voice clone ID; repeat for multiple voices.")
    parser.add_argument("--variants", type=int, default=4, choices=range(1, 9))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=default_output_root(),
        help="Cue-pack root served by /api/voice/cues.",
    )
    parser.add_argument("--language", default="English")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--server-url",
        default=str(os.environ.get("OMNIX_TTS_URL") or DEFAULT_TTS_SERVER_URL),
        help="Running Omnix TTS service URL. Defaults to OMNIX_TTS_URL or http://127.0.0.1:5101.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Per-request timeout in seconds when using the TTS service.",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Load the active TTS provider in this Python process instead of calling the running TTS service.",
    )
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

    provider = load_in_process_provider() if args.in_process else None
    if not args.in_process:
        require_ready_tts_server(args.server_url, timeout=min(args.timeout, 15.0))

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

                if args.in_process:
                    pcm_bytes, sample_rate = synthesize_in_process(
                        provider,
                        voice_id=voice_id,
                        text=prompt,
                        language=args.language,
                        variant=variant,
                    )
                    write_pcm_wav(output, pcm_bytes, sample_rate)
                    sample_count = len(pcm_bytes) // 2
                else:
                    wav_bytes, sample_rate, sample_count = synthesize_via_server(
                        args.server_url,
                        voice_id=voice_id,
                        text=prompt,
                        language=args.language,
                        variant=variant,
                        timeout=args.timeout,
                    )
                    write_wav_payload(output, wav_bytes)

                generated.append(
                    {
                        "voice_id": voice_id,
                        "cue_id": cue_id,
                        "variant_id": variant_id,
                        "path": str(output),
                        "sample_rate": sample_rate,
                        "samples": sample_count,
                        "experimental_nonverbal": cue_id in EXPERIMENTAL_NONVERBAL_PROMPTS,
                        "source": "in_process" if args.in_process else "tts_server",
                    }
                )

    print(json.dumps({"generated": generated, "skipped": skipped}, indent=2))
    return 0


def require_ready_tts_server(server_url: str, *, timeout: float) -> None:
    health_url = f"{server_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SystemExit(
            f"Could not reach a ready Omnix TTS service at {health_url}: {exc}. "
            "Start the TTS launcher service or pass --server-url."
        ) from exc
    if not payload.get("ok"):
        raise SystemExit(
            f"Omnix TTS service is not ready at {health_url}: "
            f"{payload.get('error') or payload.get('status') or 'unknown error'}"
        )


def synthesize_via_server(
    server_url: str,
    *,
    voice_id: str,
    text: str,
    language: str,
    variant: int,
    timeout: float,
) -> tuple[bytes, int, int]:
    payload = json.dumps(
        {
            "text": text,
            "speaker": voice_id,
            "language": language,
            "chunk_size": 8,
            "temperature": min(0.85, 0.56 + variant * 0.04),
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.05,
            "append_silence": False,
            "max_new_tokens": 64,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{server_url.rstrip('/')}/api/tts/generate_stream_audio",
        data=payload,
        headers={"Accept": "audio/wav", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type") or "").lower()
            wav_bytes = response.read()
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"TTS server returned HTTP {exc.code}: {details}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"TTS server request failed for {voice_id!r}: {exc}") from exc

    if "audio/wav" not in content_type and "audio/x-wav" not in content_type:
        preview = wav_bytes[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"TTS server returned {content_type or 'unknown content type'} instead of WAV: {preview}")
    sample_rate, sample_count = inspect_wav(wav_bytes)
    return wav_bytes, sample_rate, sample_count


def inspect_wav(wav_bytes: bytes) -> tuple[int, int]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            sample_count = handle.getnframes()
    except (wave.Error, EOFError) as exc:
        raise RuntimeError(f"TTS server returned an invalid WAV payload: {exc}") from exc
    if channels != 1 or sample_width != 2 or sample_rate <= 0 or sample_count <= 0:
        raise RuntimeError(
            "TTS server returned an unsupported WAV payload: "
            f"channels={channels}, sample_width={sample_width}, sample_rate={sample_rate}, samples={sample_count}"
        )
    return sample_rate, sample_count


def load_in_process_provider() -> Any:
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from app.shared import get_tts_provider

    provider = get_tts_provider()
    if provider is None or not hasattr(provider, "generate_audio_stream"):
        raise SystemExit("The active in-process TTS provider does not support streaming generation.")
    return provider


def synthesize_in_process(
    provider: Any,
    *,
    voice_id: str,
    text: str,
    language: str,
    variant: int,
) -> tuple[bytes, int]:
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from app.gateway.tts_stream_contract import audio_chunk_to_pcm16_bytes

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


def write_pcm_wav(path: Path, pcm_bytes: bytes, sample_rate: int) -> None:
    temporary = path.with_suffix(".wav.tmp")
    with wave.open(str(temporary), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm_bytes)
    temporary.replace(path)


def write_wav_payload(path: Path, wav_bytes: bytes) -> None:
    temporary = path.with_suffix(".wav.tmp")
    temporary.write_bytes(wav_bytes)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
