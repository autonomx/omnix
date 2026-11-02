"""Which voices may be cast, and to whom (evolution roadmap EV-13).

The voice library (``resources/voice_clones``) holds clone profiles of every kind: some are clones of real people or of
other works' characters, and nothing in a profile says so. ``casting.json`` beside them is the castable list: a voice
is cast automatically, or offered to other players, only when it is listed there as castable, with a description to
cast it by. Each voice's revision is a hash of its reference recording and transcript, so a cast pins the voice it
was given. ``default`` is the speech service's own voice, always castable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.assets.canonical_voice_clones import canonical_voice_clone_root

from app.caching.bounded_cache import bounded_lru_cache

DEFAULT_VOICE = "default"


def _casting(root: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads((root / "casting.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    voices = payload.get("voices") if isinstance(payload, dict) else None
    return {str(key): dict(value) for key, value in (voices or {}).items() if isinstance(value, dict)}


def _revision(root: Path, voice_id: str) -> str:
    """A hash of the voice's reference recording and transcript ("" for the service's own voice)."""
    if voice_id == DEFAULT_VOICE:
        return "service"
    profile = root / f"{voice_id}.json"
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    digest = hashlib.sha256(str(data.get("ref_text") or "").encode("utf-8"))
    for audio in sorted(root.glob(f"{voice_id}.*")):
        if audio.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg"}:
            digest.update(audio.read_bytes())
    return digest.hexdigest()[:16]


@bounded_lru_cache(max_entries=4, ttl_seconds=3600.0)
def _catalog(root: str) -> tuple[dict[str, Any], ...]:
    path = Path(root)
    voices = []
    for voice_id, row in sorted(_casting(path).items()):
        revision = _revision(path, voice_id)
        if not revision:
            continue  # listed, but no profile is there
        voices.append({"voice_id": voice_id, "name": str(row.get("name") or voice_id),
                       "description": str(row.get("description") or ""), "castable": row.get("castable") is True,
                       "revision": revision})
    return tuple(voices)


def castable_voices(root: Path | None = None) -> list[dict[str, Any]]:
    """The voices that may be cast automatically or offered: each with its description and revision."""
    return [dict(row) for row in _catalog(str(root or canonical_voice_clone_root())) if row["castable"]]


def split_sentences(text: str, *, max_chars: int = 240) -> list[str]:
    """``text`` by sentence (its closing quote kept), so a long block is heard from its first sentence; a sentence
    running past ``max_chars`` is cut at the word that passes it."""
    import re

    ends = re.compile(r"[.!?…][\"”’')\]]*$")
    sentences: list[str] = []
    words: list[str] = []
    for word in text.split():
        words.append(word)
        if ends.search(word) or len(" ".join(words)) > max_chars:
            sentences.append(" ".join(words))
            words = []
    if words:
        sentences.append(" ".join(words))
    return sentences


def render_key(text: str, *, voice_id: str, revision: str, provider: str, model: str = "", language: str = "",
               parameters: dict[str, Any] | None = None) -> str:
    """A sentence's full render identity (as audiobook's render keys are): its text, the voice and its revision (the
    reference recording's and transcript's hash), the provider and model, the language and parameters."""
    identity = json.dumps({"text": " ".join(text.split()), "voice": voice_id, "revision": revision,
                           "provider": provider, "model": model, "language": language, "parameters": parameters or {}},
                          sort_keys=True, ensure_ascii=False)
    return "speech:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def as_wav(audio: bytes, *, sample_rate: int) -> bytes:
    """The service's audio as a WAV file: kept as it is when it is one, else 16-bit mono PCM wrapped."""
    import io
    import wave

    if audio[:4] == b"RIFF":
        return audio
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(audio)
    return buffer.getvalue()


def pcm_of(audio: bytes) -> tuple[bytes, int]:
    """A WAV file's 16-bit mono samples and sample rate (the campaign's cache keeps WAV; speech is played as PCM)."""
    import io
    import wave

    with wave.open(io.BytesIO(audio), "rb") as source:
        return source.readframes(source.getnframes()), source.getframerate()


__all__ = ["DEFAULT_VOICE", "as_wav", "castable_voices", "pcm_of", "render_key", "split_sentences"]
