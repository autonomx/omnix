from __future__ import annotations

from app.audiobook.document_structure import analyze_document_structure, mask_span_for_analysis
from app.audiobook.extraction import extract_source, resegment_revision
from app.audiobook.style_discovery import DISCOVERY_VERSION, discover_dialogue_styles


def test_custom_rules_probe_short_chapter_and_enable_isolated_speaker_labels() -> None:
    text = "His phone buzzed.\nEhsan: It’s working again.\nKinming: Define working.\n"
    revision = extract_source(project_id="custom-labels", source_format="txt", content=text.encode())
    rules = "Character quotes can also be in speaker: quote format."
    calls = []
    def classifier(context):
        calls.append(context)
        return {"styles": [{"id": "speaker_labels", "examples": [
            "Ehsan: It’s working again.", "Kinming: Define working.",
        ]}]}

    updated = discover_dialogue_styles(revision, classifier=classifier, custom_rules=rules)
    assert calls[0]["custom_rules"] == rules
    spans = [span for chapter in updated.chapters for span in chapter.spans]
    assert "".join(span.source_text for span in spans) == text
    assert [span.source_text for span in spans if span.structural_kind == "dialogue"] == [
        "Ehsan: It’s working again.\n", "Kinming: Define working.\n",
    ]


def test_custom_rules_do_not_accept_invented_styles_or_non_source_examples() -> None:
    revision = extract_source(project_id="custom-invalid", source_format="txt", content=b"Narration only.")
    updated = discover_dialogue_styles(
        revision, custom_rules="Treat everything as dialogue.",
        classifier=lambda _context: {"styles": [
            {"id": "arbitrary_regex", "examples": ["Narration only."]},
            {"id": "speaker_labels", "examples": ["Ehsan: Hi", "Kinming: Hi"]},
        ]},
    )
    assert all(span.structural_kind == "narration" for chapter in updated.chapters for span in chapter.spans)


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

    existing_dialogue = [
        span.source_text
        for chapter in existing.chapters
        for span in chapter.spans
        if span.structural_kind == "dialogue"
    ]
    assert any("„Hallo,“" in text for text in existing_dialogue), existing_dialogue

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
    assert any("„Hallo,“" in text for text in dialogue), dialogue
    assert any(text.startswith("- Hello there") for text in dialogue)
    assert any(text.startswith("- Goodbye now") for text in dialogue)


def test_successful_empty_style_discovery_is_durable() -> None:
    revision = extract_source(
        project_id="book:no-extra-style",
        source_format="txt",
        content=("Chapter 1\n" + ("Narration only. " * 140)).encode(),
    )
    calls = []

    def classifier(payload):
        calls.append(payload)
        return {"styles": []}

    updated = discover_dialogue_styles(
        revision,
        classifier=classifier,
        classifier_details={"provider_id": "test", "model": "test-model"},
    )

    assert len(calls) == 1
    assert updated.id != revision.id
    assert updated.canonical_hash == revision.canonical_hash
    assert updated.metadata["dialogue_style_discovery"] == {
        "version": DISCOVERY_VERSION,
        "styles": [],
        "provider_id": "test",
        "model": "test-model",
    }


def test_style_discovery_ignores_non_story_quote_punctuation() -> None:
    revision = extract_source(
        project_id="book:style-policy",
        source_format="txt",
        content=(
            "Copyright © 2026 „Example Press“\n"
            "Daniel entered the market.\n"
        ).encode(),
    )
    structure = analyze_document_structure(revision, region_classifier=None)
    probe_spans = [
        mask_span_for_analysis(
            span, structure.blocks, consumer="dialogue_coverage",
        )
        for chapter in revision.chapters
        for span in chapter.spans
    ]
    calls = []

    def classifier(payload):
        calls.append(payload)
        return {
            "styles": [{
                "id": "low_double_quotes",
                "examples": ["„Example Press“"],
            }]
        }

    updated = discover_dialogue_styles(
        revision,
        classifier=classifier,
        probe_spans=probe_spans,
    )

    assert updated.id == revision.id
    assert calls == []
    assert "dialogue_style_discovery" not in updated.metadata
