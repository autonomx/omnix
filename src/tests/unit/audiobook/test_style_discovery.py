from __future__ import annotations

from app.audiobook.extraction import extract_source, resegment_revision
from app.audiobook.style_discovery import DISCOVERY_VERSION, discover_dialogue_styles


def test_style_rediscovery_preserves_existing_verified_styles() -> None:
    base = extract_source(
        project_id="book:additive-style-discovery",
        source_format="txt",
        content=(
            "Chapter 1\n"
            "„Hallo,“ sagte Nita.\n"
            "- Hello there\n"
            "- Goodbye now\n"
        ).encode(),
    )
    existing = resegment_revision(
        base,
        styles=("low_double_quotes",),
        discovery={
            "version": DISCOVERY_VERSION,
            "styles": ["low_double_quotes"],
            "provider_id": "prior-provider",
            "model": "prior-model",
        },
    )

    def classifier(payload):
        assert payload["task"] == "discover_dialogue_style"
        return {
            "styles": [{
                "id": "hyphen_dash",
                "examples": ["- Hello there", "- Goodbye now"],
            }]
        }

    updated = discover_dialogue_styles(
        existing,
        classifier=classifier,
        classifier_details={"provider_id": "test", "model": "test-model"},
    )

    discovery = updated.metadata["dialogue_style_discovery"]
    assert set(discovery["styles"]) == {"low_double_quotes", "hyphen_dash"}
    dialogue = [
        span.source_text
        for chapter in updated.chapters
        for span in chapter.spans
        if span.structural_kind == "dialogue"
    ]
    assert any("„Hallo,“" in text for text in dialogue)
    assert any(text.startswith("- Hello there") for text in dialogue)
    assert any(text.startswith("- Goodbye now") for text in dialogue)
