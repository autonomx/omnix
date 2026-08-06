from __future__ import annotations

from app.providers.kyutai_live_stt import KyutaiLiveSttSession
from app.providers.kyutai_transcript_normalization import (
    install_kyutai_transcript_normalization,
    join_kyutai_word_tokens,
)


def test_join_kyutai_word_tokens_restores_word_boundaries() -> None:
    assert join_kyutai_word_tokens(
        ["What", "kind", "of", "nonsense", "?"]
    ) == "What kind of nonsense?"


def test_join_kyutai_word_tokens_preserves_punctuation_and_contractions() -> None:
    assert join_kyutai_word_tokens(
        ["That", "'s", "wild", ",", "right", "?"]
    ) == "That's wild, right?"


def test_runtime_installer_replaces_legacy_empty_join() -> None:
    install_kyutai_transcript_normalization()
    session = object.__new__(KyutaiLiveSttSession)
    session._transcript_parts = ["What", "kind", "of", "nonsense", "?"]

    assert session.transcript == "What kind of nonsense?"
