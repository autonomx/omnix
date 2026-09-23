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
