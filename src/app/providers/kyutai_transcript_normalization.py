"""Normalize Kyutai word tokens into readable transcripts."""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.providers.kyutai_live_stt import KyutaiLiveSttSession

_PATCH_FLAG = "_omnix_transcript_spacing_installed"
_NO_SPACE_BEFORE = re.compile(r"^[,.;:!?%\]\)}…]")
_CONTRACTION = re.compile(r"^(?:n't|'(?:s|re|ve|ll|d|m))\b", re.IGNORECASE)


def join_kyutai_word_tokens(tokens: Iterable[object]) -> str:
    """Join tokenized words while preserving punctuation and contractions."""

    transcript = ""
    for value in tokens:
        token = " ".join(str(value or "").split())
        if not token:
            continue
        if not transcript:
            transcript = token
            continue
        if (
            _NO_SPACE_BEFORE.match(token)
            or _CONTRACTION.match(token)
            or transcript.endswith((" ", "-", "—", "/", "(", "[", "{", "'"))
        ):
            transcript += token
        else:
            transcript += f" {token}"
    return transcript.strip()


def install_kyutai_transcript_normalization() -> None:
    """Install the token joiner on the Kyutai runtime session class once."""

    session_type: Any = KyutaiLiveSttSession
    if getattr(session_type, _PATCH_FLAG, False):
        return
    session_type.transcript = property(
        lambda session: join_kyutai_word_tokens(session._transcript_parts)
    )
    setattr(session_type, _PATCH_FLAG, True)
