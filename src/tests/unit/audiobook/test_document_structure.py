from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.audiobook.document_structure import (
    ANALYSIS_POLICY_VERSION,
    DOCUMENT_STRUCTURE_VERSION,
    RENDER_POLICY_VERSION,
    EXCLUDE,
    READ,
    SKIP,
    analysis_policy,
    analyze_document_structure,
    dialogue_targets_for_analysis,
    effective_render_action,
    effective_role,
    mask_span_for_analysis,
    mask_span_for_render,
    render_policy,
)
from app.audiobook.extraction import extract_source


_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "audiobook"
    / "document_structure_golden.json"
)


def _revision(case: dict[str, object]):
    revision = extract_source(
        project_id=f"book:{case['name']}",
        content=str(case["text"]).encode(),
        source_format="text",
    )
    metadata = dict(revision.metadata)
    metadata.update(dict(case.get("metadata") or {}))
    source_format = str(case.get("source_format_override") or revision.source_format)
    return replace(revision, source_format=source_format, metadata=metadata)


def _target_block(analysis, target: str):
    return next(
        block for block in analysis.blocks
        if block.original_text.strip() == target
    )


_GOLDEN = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _GOLDEN, ids=lambda item: item["name"])
def test_document_structure_golden(case: dict[str, object]) -> None:
    analysis = analyze_document_structure(_revision(case))
    block = _target_block(analysis, str(case["target"]))

    assert analysis.version == DOCUMENT_STRUCTURE_VERSION
    assert block.content_role == case["role"]
    assert any(
        item.get("source") == case["provenance"]
        for item in block.provenance
    )
    assert render_policy(block.content_role, "standard") == case["standard"]
    assert render_policy(block.content_role, "story_only") == case["story_only"]
    assert render_policy(block.content_role, "verbatim") == case["verbatim"]
    assert analysis_policy(block.content_role, "speaker_attribution") == case["speaker"]
    assert block.parent_block_id
    assert any(
        region.id == block.parent_block_id and block.id in region.block_ids
        for region in analysis.regions
    )


def test_toc_entries_do_not_create_fake_canonical_chapters() -> None:
    revision = extract_source(
        project_id="book:toc-boundaries",
        source_format="text",
        content=(
            "CONTENTS\n"
            "Chapter One ........ 1\n"
            "Chapter Two ........ 17\n"
            "Chapter One\n"
            "Daniel opened the gate.\n"
        ).encode(),
    )
    assert len(revision.chapters) == 2
    assert revision.chapters[0].title == "Opening"
    assert "Chapter One ........ 1" in revision.chapters[0].canonical_text
    assert revision.chapters[1].title == "Chapter One"


def test_analysis_mask_removes_metadata_but_preserves_source_and_story() -> None:
    revision = extract_source(
        project_id="book:analysis-mask",
        source_format="text",
        content=b"Page 1 of 3\nDaniel walked into town.\n",
    )
    chapter = revision.chapters[0]
    analysis = analyze_document_structure(revision)
    original = chapter.spans[0]
    masked = mask_span_for_analysis(
        original, analysis.blocks, consumer="speaker_attribution",
    )

    assert original.source_text == "Page 1 of 3\nDaniel walked into town.\n"
    assert "Page 1 of 3" not in masked.source_text
    assert "Daniel walked into town." in masked.source_text
    assert masked.id == original.id
    assert masked.start_offset == original.start_offset
    assert masked.end_offset == original.end_offset


def test_render_mask_skips_metadata_without_mutating_canonical_source() -> None:
    revision = extract_source(
        project_id="book:render-mask",
        source_format="text",
        content=b"Page 1 of 3\nDaniel walked into town.\n",
    )
    chapter = revision.chapters[0]
    analysis = analyze_document_structure(revision)
    original = chapter.spans[0]

    standard = mask_span_for_render(
        original, analysis.blocks, mode="standard",
    )
    verbatim = mask_span_for_render(
        original, analysis.blocks, mode="verbatim",
    )

    assert original.source_text == "Page 1 of 3\nDaniel walked into town.\n"
    assert "Page 1 of 3" not in standard
    assert "Daniel walked into town." in standard
    assert verbatim == original.source_text


def test_story_structure_remains_visible_to_speaker_analysis_context() -> None:
    revision = extract_source(
        project_id="book:heading-context",
        source_format="text",
        content=b"Chapter One\nDaniel entered the market.\n",
    )
    analysis = analyze_document_structure(revision)
    chapter = next(ch for ch in revision.chapters if ch.title == "Chapter One")
    masked = "".join(
        mask_span_for_analysis(
            span, analysis.blocks, consumer="speaker_attribution",
        ).source_text
        for span in chapter.spans
    )

    assert "Chapter One" in masked
    assert "Daniel entered the market." in masked


def test_ai_fallback_receives_contiguous_ambiguous_region_and_can_return_unknown() -> None:
    revision = extract_source(
        project_id="book:ambiguous-region",
        source_format="text",
        content=b"North Gate\nWinter Court\nDaniel crossed the bridge.\n",
    )
    calls: list[dict[str, object]] = []

    def classifier(payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        region = payload["region"]
        assert isinstance(region, list)
        return {
            "blocks": [
                {
                    "block_id": region[0]["block_id"],
                    "content_role": "scene_heading",
                    "confidence": 0.93,
                },
                {
                    "block_id": region[1]["block_id"],
                    "content_role": "unknown",
                    "confidence": 0.55,
                },
            ]
        }

    analysis = analyze_document_structure(revision, region_classifier=classifier)

    assert len(calls) == 1
    assert [item["text"] for item in calls[0]["region"]] == [
        "North Gate", "Winter Court",
    ]
    assert _target_block(analysis, "North Gate").content_role == "scene_heading"
    assert _target_block(analysis, "Winter Court").content_role == "unknown"
    assert analysis.ai_fallback_used is True


def test_explicit_book_title_metadata_outranks_derived_chapter_boundary() -> None:
    revision = extract_source(
        project_id="book:title-precedence",
        source_format="md",
        content=(
            "# The Gold Cart Merchant\n"
            "Daniel opened the gate.\n"
        ).encode(),
    )
    revision = replace(
        revision,
        metadata={**revision.metadata, "title": "The Gold Cart Merchant"},
    )

    analysis = analyze_document_structure(revision)
    title = _target_block(analysis, "# The Gold Cart Merchant")

    assert title.content_role == "book_title"
    assert any(
        item.get("source") == "source_metadata"
        and item.get("signal") == "title_match"
        for item in title.provenance
    )


def test_markdown_heading_syntax_is_structural_not_source_mutation() -> None:
    revision = extract_source(
        project_id="book:markdown-structure",
        source_format="md",
        content=(
            "# Contents\n"
            "Chapter One ........ 1\n"
            "# Preface\n"
            "This edition began as a small project.\n"
            "# Chapter One\n"
            "Daniel opened the gate.\n"
        ).encode(),
    )
    analysis = analyze_document_structure(revision)

    contents = _target_block(analysis, "# Contents")
    preface = _target_block(analysis, "# Preface")
    chapter = _target_block(analysis, "# Chapter One")

    assert contents.content_role == "table_of_contents"
    assert preface.content_role == "preface"
    assert chapter.content_role == "chapter_heading"
    assert contents.original_text == "# Contents"
    assert preface.original_text == "# Preface"
    assert chapter.original_text == "# Chapter One"


def test_low_confidence_ai_fallback_cannot_suppress_unknown_text() -> None:
    revision = extract_source(
        project_id="book:weak-structure-guess",
        source_format="text",
        content=b"North Gate\nDaniel crossed the bridge.\n",
    )

    def classifier(payload: dict[str, object]) -> dict[str, object]:
        region = payload["region"]
        assert isinstance(region, list)
        return {
            "blocks": [{
                "block_id": region[0]["block_id"],
                "content_role": "table_of_contents",
                "confidence": 0.60,
            }]
        }

    analysis = analyze_document_structure(revision, region_classifier=classifier)
    block = _target_block(analysis, "North Gate")

    assert block.content_role == "unknown"
    assert render_policy(block.content_role, "standard") == READ
    assert analysis.ai_fallback_used is False
    assert any(
        item.get("source") == "ai_fallback"
        and item.get("signal") == "rejected_low_confidence"
        for item in block.provenance
    )


def test_scoped_overrides_apply_in_precedence_order() -> None:
    revision = extract_source(
        project_id="book:overrides",
        source_format="text",
        content=b"LONDON\nDaniel walked into town.\n",
    )
    analysis = analyze_document_structure(revision)
    block = _target_block(analysis, "LONDON")
    assert block.parent_block_id

    overrides = [
        {
            "scope": "DOCUMENT_ROLE",
            "scope_key": "scene_heading",
            "action": "SKIP",
            "revision": 1,
        },
        {
            "scope": "REGION",
            "scope_key": block.parent_block_id,
            "action": "READ",
            "revision": 1,
        },
        {
            "scope": "BLOCK",
            "scope_key": block.id,
            "action": "SKIP",
            "role_override": "story_text",
            "revision": 1,
        },
    ]

    assert effective_role(block, overrides) == "story_text"
    assert effective_render_action(
        block, mode="standard", overrides=overrides,
    ) == SKIP


def test_recurrence_group_is_stable_for_repeated_short_text() -> None:
    revision = extract_source(
        project_id="book:recurrence",
        source_format="text",
        content=(
            "THE GOLD CART MERCHANT\n"
            "Daniel walked into town.\n"
            "THE GOLD CART MERCHANT\n"
            "Mara closed the gate.\n"
        ).encode(),
    )
    analysis = analyze_document_structure(revision)
    repeated = [
        block for block in analysis.blocks
        if block.original_text == "THE GOLD CART MERCHANT"
    ]
    assert len(repeated) == 2
    assert repeated[0].recurrence_group
    assert repeated[0].recurrence_group == repeated[1].recurrence_group


def test_policy_versions_are_explicit_and_independent() -> None:
    assert DOCUMENT_STRUCTURE_VERSION == "document-role-v1"
    assert RENDER_POLICY_VERSION == "audiobook-render-policy-v1"
    assert ANALYSIS_POLICY_VERSION == "audiobook-analysis-policy-v1"
    assert analysis_policy("page_number", "speaker_attribution") == EXCLUDE
    assert render_policy("story_text", "standard") == READ


def test_optional_dialogue_is_context_only_not_a_speaker_target() -> None:
    revision = extract_source(
        project_id="book:optional-dialogue",
        source_format="text",
        content=(
            'PREFACE\n'
            '“A quoted memory,” Nita said.\n'
            'Chapter One\n'
            '“Open the gate,” Daniel said.\n'
        ).encode(),
    )
    analysis = analyze_document_structure(revision)
    targets = dialogue_targets_for_analysis(
        [
            span
            for chapter in revision.chapters
            for span in chapter.spans
        ],
        analysis.blocks,
        consumer="speaker_attribution",
    )
    preface = next(
        chapter for chapter in revision.chapters
        if "PREFACE" in chapter.canonical_text
    )
    story = next(
        chapter for chapter in revision.chapters
        if chapter.title == "Chapter One"
    )
    preface_dialogue = next(
        span for span in preface.spans if span.structural_kind == "dialogue"
    )
    story_dialogue = next(
        span for span in story.spans if span.structural_kind == "dialogue"
    )

    assert preface_dialogue.id not in targets
    assert story_dialogue.id in targets


def test_pdf_recurrence_does_not_hide_identical_body_occurrence() -> None:
    revision = extract_source(
        project_id="book:pdf-body-recurrence",
        source_format="text",
        content=(
            "THE GOLD CART MERCHANT\n"
            "Daniel entered the square.\n"
            "THE GOLD CART MERCHANT\n"
            "Mara pointed at the sign.\n"
            "THE GOLD CART MERCHANT\n"
            "The market opened.\n"
        ).encode(),
    )
    revision = replace(
        revision,
        source_format="pdf",
        metadata={
            "pdf_page_blocks": [
                {
                    "page_index": 0, "block_index": 0, "reading_order": 0,
                    "original_text": "THE GOLD CART MERCHANT",
                    "distance_from_top": 0.0, "distance_from_bottom": 1.0,
                },
                {
                    "page_index": 1, "block_index": 8, "reading_order": 8,
                    "original_text": "THE GOLD CART MERCHANT",
                    "distance_from_top": 0.5, "distance_from_bottom": 0.5,
                },
                {
                    "page_index": 2, "block_index": 0, "reading_order": 0,
                    "original_text": "THE GOLD CART MERCHANT",
                    "distance_from_top": 0.0, "distance_from_bottom": 1.0,
                },
            ]
        },
    )
    analysis = analyze_document_structure(revision)
    repeated = [
        block for block in analysis.blocks
        if block.original_text == "THE GOLD CART MERCHANT"
    ]

    assert [block.content_role for block in repeated] == [
        "running_header", "unknown", "running_header",
    ]
    assert repeated[0].page_index == 0
    assert repeated[1].distance_from_top == 0.5
    assert render_policy(repeated[0].content_role, "standard") == SKIP
    assert render_policy(repeated[1].content_role, "standard") == READ
