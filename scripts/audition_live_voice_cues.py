#!/usr/bin/env python3
"""Make candidate sound clips ([chuckle], [sigh]) in a cloned voice and keep the takes that pass, for the owner to hear.

Each take comes from the running TTS service in the voice's clone and is then checked:

- length: the sound itself (quiet ends not counted) lasts as long as a short nonverbal sound does;
- loudness: it is neither near-silent nor clipped;
- likeness: the speech service's speaker model (TitaNet) scores it against the voice's clone clip no worse than the
  voice's own hmm/mhm clips score, less a margin, since a sound scores below speech.

Passing takes are trimmed to the sound and written to ``<out>/<voice>/passed``; the others go to ``rejected`` with
the reason, and ``report.json`` holds every score. Nothing plays in a call until chosen takes are copied into the cue
root as ``<cue>-v1.wav`` .. ``<cue>-v4.wav``. Needs the TTS and speech services running.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import statistics
import sys
import wave
from array import array
from pathlib import Path
from typing import Any

from generate_live_voice_cue_pack import (
    DEFAULT_TTS_SERVER_URL,
    REPO_ROOT,
    SRC_ROOT,
    default_output_root,
    require_ready_tts_server,
    synthesize_via_server,
)

# Several spellings per sound: the clone renders each a little differently, and the checks pick the takes.
# Trailing ellipses and breathy spellings draw out softer, longer renderings; the owner judged
# short, loud takes (a spoken "Heh.") as not a real exhale or sigh (2026-11-15).
AUDITION_PROMPTS: dict[str, tuple[str, ...]] = {
    "amused_exhale": ("Heh.", "heh...", "Hm, heh...", "Hehh..."),
    "sigh": ("Haaah...", "Ahh...", "Hhhaaah...", "Mmhhh..."),
}
SOUND_SECONDS: dict[str, tuple[float, float]] = {
    "amused_exhale": (0.45, 1.6),
    "sigh": (0.6, 2.2),
}
_FRAME_SECONDS = 0.01
_SOUND_FLOOR_DBFS = -45.0  # a frame quieter than this is not part of the sound
_MIN_SOUND_DBFS = -38.0  # the sound's average level; quieter is a near-silent take
_MAX_SOUND_DBFS = -16.0  # the raw take's average level; louder is a forceful, spoken rendering
_MAX_PEAK_DBFS = -0.3  # louder is clipped
_SOFT_TARGET_DBFS = -21.0  # softened takes are turned down to this average level, never up
_FADE_IN_SECONDS = 0.04
_FADE_OUT_SHARE = 0.4  # the last 40% of the sound fades out
_TRIM_PAD_SECONDS = 0.03
_LIKENESS_MARGIN = 0.15
_FALLBACK_MIN_LIKENESS = 0.3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voice", action="append", required=True, help="Voice clone ID; repeat for several voices.")
    parser.add_argument("--cue", action="append", choices=sorted(AUDITION_PROMPTS), help="Default: every sound.")
    parser.add_argument("--candidates", type=int, default=12, help="Takes to make per sound and voice.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "resources" / "cache" / "voice_cue_auditions",
        help="Where candidate takes and the report go (never the served cue root).",
    )
    parser.add_argument("--cue-root", type=Path, default=default_output_root(), help="The served cue root.")
    parser.add_argument("--clone-dir", type=Path, default=None, help="Folder of <voice>.wav clone clips.")
    parser.add_argument("--min-likeness", type=float, default=None, help="Override the voice's likeness floor.")
    parser.add_argument("--language", default="English")
    parser.add_argument("--server-url", default=str(os.environ.get("OMNIX_TTS_URL") or DEFAULT_TTS_SERVER_URL))
    parser.add_argument("--stt-url", default=None, help="Speech service base URL; default from the runtime config.")
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_root.resolve() == args.cue_root.resolve():
        raise SystemExit("Auditions must not be written into the served cue root.")
    load_service_token()
    require_ready_tts_server(args.server_url, timeout=min(args.timeout, 15.0))
    stt_url = (args.stt_url or runtime_stt_url()).rstrip("/")
    cues = args.cue or sorted(AUDITION_PROMPTS)
    summary: list[dict[str, Any]] = []
    for voice_id in args.voice:
        summary.append(audition_voice(args, stt_url, voice_id.strip(), cues))
    print(json.dumps(summary, indent=2))
    return 0


def audition_voice(args: argparse.Namespace, stt_url: str, voice_id: str, cues: list[str]) -> dict[str, Any]:
    if not voice_id or any(character in voice_id for character in "/\\") or voice_id in {".", ".."}:
        raise SystemExit(f"Invalid voice ID: {voice_id!r}")
    reference = clone_clip_path(voice_id, args.clone_dir)
    reference_embedding = unit(embed(stt_url, reference.read_bytes(), reference.name))
    if reference_embedding is None:
        raise SystemExit(f"The speech service gave no speaker embedding for {reference}.")

    baseline = baseline_likeness(stt_url, args.cue_root / voice_id, reference_embedding)
    if args.min_likeness is not None:
        floor = args.min_likeness
    elif baseline:
        floor = round(statistics.median(baseline.values()) - _LIKENESS_MARGIN, 4)
    else:
        floor = _FALLBACK_MIN_LIKENESS

    voice_dir = args.output_root / voice_id
    passed_dir, rejected_dir = voice_dir / "passed", voice_dir / "rejected"
    passed_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    takes: list[dict[str, Any]] = []
    for cue_id in cues:
        prompts = AUDITION_PROMPTS[cue_id]
        for index in range(args.candidates):
            prompt = prompts[index % len(prompts)]
            wav_bytes, sample_rate, _count = synthesize_via_server(
                args.server_url,
                voice_id=voice_id,
                text=prompt,
                language=args.language,
                variant=1 + index % 7,
                timeout=args.timeout,
            )
            pcm = read_pcm(wav_bytes)
            measured = measure(pcm, sample_rate)
            trimmed = soften(trim(pcm, sample_rate, measured), sample_rate)
            score = likeness(stt_url, trimmed, sample_rate, reference_embedding)
            reasons = check(cue_id, measured, score, floor)
            name = f"{cue_id}-c{index + 1:02d}.wav"
            target = (rejected_dir if reasons else passed_dir) / name
            write_wav(target, trimmed, sample_rate)
            takes.append({
                "cue_id": cue_id,
                "file": str(target),
                "prompt": prompt,
                "passed": not reasons,
                "reasons": reasons,
                "likeness": score,
                **measured,
            })

    report = {
        "voice_id": voice_id,
        "reference": str(reference),
        "likeness_floor": floor,
        "baseline_likeness": baseline,
        "takes": takes,
    }
    (voice_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {
        "voice_id": voice_id,
        "likeness_floor": floor,
        "baseline_likeness": baseline,
        "passed": {cue: sum(1 for take in takes if take["cue_id"] == cue and take["passed"]) for cue in cues},
        "folder": str(voice_dir),
    }


def check(cue_id: str, measured: dict[str, float], score: float | None, floor: float) -> list[str]:
    reasons: list[str] = []
    shortest, longest = SOUND_SECONDS[cue_id]
    if not shortest <= measured["sound_seconds"] <= longest:
        reasons.append(f"length {measured['sound_seconds']:.2f}s outside {shortest}-{longest}s")
    if measured["sound_dbfs"] < _MIN_SOUND_DBFS:
        reasons.append(f"too quiet ({measured['sound_dbfs']:.1f} dBFS)")
    if measured["sound_dbfs"] > _MAX_SOUND_DBFS:
        reasons.append(f"too forceful ({measured['sound_dbfs']:.1f} dBFS)")
    if measured["peak_dbfs"] > _MAX_PEAK_DBFS:
        reasons.append(f"clipped (peak {measured['peak_dbfs']:.1f} dBFS)")
    if score is None:
        reasons.append("no likeness score")
    elif score < floor:
        reasons.append(f"likeness {score:.3f} below {floor:.3f}")
    return reasons


# --- Audio -------------------------------------------------------------------------------------------------------


def read_pcm(wav_bytes: bytes) -> array:
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    samples = array("h")
    samples.frombytes(frames[: len(frames) - len(frames) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def dbfs(value: float) -> float:
    return 20.0 * math.log10(value / 32768.0) if value > 0 else -120.0


def measure(samples: array, sample_rate: int) -> dict[str, float]:
    frame = max(1, int(sample_rate * _FRAME_SECONDS))
    levels = []
    for start in range(0, len(samples), frame):
        chunk = samples[start:start + frame]
        levels.append(dbfs(math.sqrt(sum(value * value for value in chunk) / len(chunk))) if chunk else -120.0)
    loud = [index for index, level in enumerate(levels) if level >= _SOUND_FLOOR_DBFS]
    if not loud:
        return {"sound_seconds": 0.0, "sound_dbfs": -120.0, "peak_dbfs": -120.0, "sound_start": 0, "sound_end": 0}
    start, end = loud[0] * frame, min(len(samples), (loud[-1] + 1) * frame)
    sound = samples[start:end]
    mean_square = sum(value * value for value in sound) / len(sound)
    return {
        "sound_seconds": round((end - start) / sample_rate, 3),
        "sound_dbfs": round(dbfs(math.sqrt(mean_square)), 2),
        "peak_dbfs": round(dbfs(max(abs(value) for value in sound)), 2),
        "sound_start": start,
        "sound_end": end,
    }


def trim(samples: array, sample_rate: int, measured: dict[str, float]) -> array:
    if measured["sound_end"] <= measured["sound_start"]:
        return samples
    pad = int(sample_rate * _TRIM_PAD_SECONDS)
    return samples[max(0, int(measured["sound_start"]) - pad):min(len(samples), int(measured["sound_end"]) + pad)]


def soften(samples: array, sample_rate: int) -> array:
    """Fade the take in briefly and out over its tail, and turn it down to the soft level if louder."""
    count = len(samples)
    if count == 0:
        return array("h", samples)
    mean_square = sum(value * value for value in samples) / count
    level = dbfs(math.sqrt(mean_square))
    gain = 10.0 ** ((_SOFT_TARGET_DBFS - level) / 20.0) if level > _SOFT_TARGET_DBFS else 1.0
    fade_in = max(1, int(sample_rate * _FADE_IN_SECONDS))
    fade_out = max(1, int(count * _FADE_OUT_SHARE))
    softened = array("h")
    for index, value in enumerate(samples):
        envelope = 1.0
        if index < fade_in:
            envelope = math.sin(0.5 * math.pi * index / fade_in)
        remaining = count - 1 - index
        if remaining < fade_out:
            envelope *= math.sin(0.5 * math.pi * remaining / fade_out)
        softened.append(max(-32768, min(32767, round(value * gain * envelope))))
    return softened


def wav_bytes_of(samples: array, sample_rate: int) -> bytes:
    data = array("h", samples)
    if sys.byteorder == "big":
        data.byteswap()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(data.tobytes())
    return buffer.getvalue()


def write_wav(path: Path, samples: array, sample_rate: int) -> None:
    temporary = path.with_suffix(".wav.tmp")
    temporary.write_bytes(wav_bytes_of(samples, sample_rate))
    temporary.replace(path)


# --- Likeness ----------------------------------------------------------------------------------------------------


def load_service_token() -> None:
    """Read the launcher's issued service credential when this shell has none; never create one."""
    if os.environ.get("OMNIX_SERVICE_TOKEN"):
        return
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from app.security.service_credentials import read_protected_token, service_credential_path

    path = service_credential_path()
    try:
        os.environ["OMNIX_SERVICE_TOKEN"] = read_protected_token(path)
    except FileNotFoundError as exc:
        raise SystemExit(f"No service credential at {path}; start Omnix with the launcher first.") from exc


def runtime_stt_url() -> str:
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from app.runtime.config import get_runtime_config

    endpoint = get_runtime_config().stt
    if endpoint is None:
        raise SystemExit("No speech service is configured; pass --stt-url.")
    return endpoint.url.removesuffix("/transcribe")


def clone_clip_path(voice_id: str, clone_dir: Path | None) -> Path:
    if clone_dir is not None:
        path = clone_dir / f"{voice_id}.wav"
    else:
        if str(SRC_ROOT) not in sys.path:
            sys.path.insert(0, str(SRC_ROOT))
        from app.providers.voice_references import clone_reference

        found = clone_reference(voice_id)[0]
        path = Path(found) if found else Path()
    if not path.is_file():
        raise SystemExit(f"No clone clip for {voice_id!r}; pass --clone-dir.")
    return path


def embed(stt_url: str, payload: bytes, filename: str) -> list[float] | None:
    import httpx

    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from app.security.service_token import service_headers

    response = httpx.post(
        f"{stt_url}/speaker/embedding",
        files={"file": (filename, payload, "application/octet-stream")},
        headers=service_headers(),
        timeout=60.0,
    )
    if response.status_code != 200:
        raise SystemExit(f"Speaker embedding failed: HTTP {response.status_code} {response.text[:300]}")
    data = response.json()
    vector = data.get("embedding") if data.get("ok") else None
    return vector if isinstance(vector, list) else None


def unit(vector: list[float] | None) -> list[float] | None:
    if not vector:
        return None
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm > 0 else None


def likeness(stt_url: str, samples: array, sample_rate: int, reference: list[float]) -> float | None:
    take = unit(embed(stt_url, wav_bytes_of(samples, sample_rate), "take.wav"))
    return None if take is None else round(sum(a * b for a, b in zip(take, reference)), 4)


def baseline_likeness(stt_url: str, voice_cue_dir: Path, reference: list[float]) -> dict[str, float]:
    """How the voice's existing hum clips (already heard and kept) score against its clone clip."""
    scores: dict[str, float] = {}
    for path in sorted(voice_cue_dir.glob("*.wav")) if voice_cue_dir.is_dir() else ():
        if not path.name.startswith(("hmm-", "mhm-")):
            continue
        vector = unit(embed(stt_url, path.read_bytes(), path.name))
        if vector is not None:
            scores[path.name] = round(sum(a * b for a, b in zip(vector, reference)), 4)
    return scores


if __name__ == "__main__":
    raise SystemExit(main())
