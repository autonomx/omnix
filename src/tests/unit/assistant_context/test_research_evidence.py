from app.research.evidence import (
    prepare_evidence_context_items,
    render_answer_with_compatibility_fallback,
    validate_plain_text_citations,
)


def evidence_item():
    return {
        "source_id": "web_search",
        "title": "Release source",
        "content": "Search snippet.",
        "url": "https://example.test/release",
        "metadata": {
            "citation_label": "S1",
            "source_record_id": "source:one",
            "snapshot_id": "snapshot:one",
            "source_manifest_id": "manifest:one",
            "extracted_excerpt": "Verified extracted evidence.",
        },
    }


def test_context_item_exposes_persisted_citation_label_and_evidence() -> None:
    prepared = prepare_evidence_context_items([evidence_item()])
    assert prepared[0]["title"].startswith("[S1]")
    assert "Citation label: [S1]" in prepared[0]["content"]
    assert "Verified extracted evidence." in prepared[0]["content"]


def test_structured_answer_requires_fact_support_and_renders_citations() -> None:
    raw = '{"sections":[{"kind":"fact","text":"The release is current.","citation_labels":["S1"]}]}'
    rendered = render_answer_with_compatibility_fallback(raw, ["S1"])
    assert rendered.content == "The release is current. [S1]"
    assert rendered.validation.valid is True
    assert rendered.validation.structured is True


def test_plain_text_fallback_is_visible_and_citation_constrained() -> None:
    rendered = render_answer_with_compatibility_fallback("The release is current [S1].", ["S1"])
    assert rendered.validation.valid is True
    assert rendered.validation.structured is False
    assert "structured output was unavailable" in rendered.content


def test_missing_and_unknown_citations_are_reported() -> None:
    missing = validate_plain_text_citations("Unsupported factual answer.", ["S1"])
    unknown = validate_plain_text_citations("Claim [S9].", ["S1"])
    assert missing.valid is False
    assert missing.missing_citations is True
    assert unknown.valid is False
    assert unknown.unknown_labels == ["S9"]
