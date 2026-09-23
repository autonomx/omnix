"""Document-level structure interpretation and consumer policies.

Immutable SourceSpan text remains canonical. This module derives block/region roles,
provenance, recurrence, and policy projections without mutating source text.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .hashing import text_hash
from .models import SourceRevision, SourceSpan


DOCUMENT_STRUCTURE_VERSION = "document-role-v1"
RENDER_POLICY_VERSION = "audiobook-render-policy-v1"
ANALYSIS_POLICY_VERSION = "audiobook-analysis-policy-v1"

READ = "READ"
SKIP = "SKIP"
READ_ONCE = "READ_ONCE"
INCLUDE = "INCLUDE"
CONTEXT_ONLY = "CONTEXT_ONLY"
EXCLUDE = "EXCLUDE"

CONTENT_ROLES = frozenset({
    "story_text", "scene_heading", "scene_break",
    "chapter_heading", "part_heading", "prologue_heading", "epilogue_heading",
    "book_title", "subtitle", "author_name",
    "dedication", "epigraph", "foreword", "preface", "author_note",
    "acknowledgements", "footnote_body", "endnote",
    "table_of_contents", "copyright", "isbn", "publisher_metadata",
    "bibliography", "index", "page_number", "running_header",
    "running_footer", "footnote_marker", "unknown",
})

OPTIONAL_ROLES = frozenset({
    "dedication", "epigraph", "foreword", "preface", "author_note",
    "acknowledgements", "footnote_body", "endnote",
})
NON_STORY_ROLES = frozenset({
    "table_of_contents", "copyright", "isbn", "publisher_metadata",
    "bibliography", "index", "page_number", "running_header",
    "running_footer", "footnote_marker",
})
STORY_STRUCTURE_ROLES = frozenset({
    "chapter_heading", "part_heading", "prologue_heading", "epilogue_heading",
})

_CHAPTER = re.compile(r"^chapter\s+(?:\d+|[ivxlcdm]+|[a-z]+)\b.*$", re.I)
_PART = re.compile(r"^part\s+(?:\d+|[ivxlcdm]+|[a-z]+)\b.*$", re.I)
_PAGE = re.compile(r"^(?:page\s+)?\d+\s*(?:of|/)\s*\d+$|^page\s+\d+$", re.I)
_ISBN = re.compile(r"\bisbn(?:-1[03])?\b", re.I)
_COPYRIGHT = re.compile(r"(?:copyright|©|all rights reserved)", re.I)
_TOC_ENTRY = re.compile(r"(?:\.{2,}|\s)\s*\d{1,4}\s*$")
_FOOTNOTE_BODY = re.compile(r"^\s*\[(\d{1,4})\]\s+\S")
_FOOTNOTE_MARKER = re.compile(r"^\s*\[(\d{1,4})\]\s*$")
_SCENE_BREAK = re.compile(r"^\s*(?:\*\s*){3,}$|^\s*(?:#\s*){3,}$|^\s*[—–-]{3,}\s*$")


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    id: str
    chapter_id: str
    ordinal: int
    start_offset: int
    end_offset: int
    source_span_ids: tuple[str, ...]
    original_text: str
    normalized_text: str
    content_role: str
    confidence: float
    provenance: tuple[dict[str, Any], ...]
    recurrence_group: str | None
    structure_quality: str
    parent_block_id: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentStructureAnalysis:
    source_revision_id: str
    version: str
    blocks: tuple[DocumentBlock, ...]
    ai_fallback_used: bool = False


def normalize_block_text(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _quality(source_format: str) -> str:
    if source_format in {"epub", "docx", "html", "htm"}:
        return "HIGH"
    if source_format == "pdf":
        return "MEDIUM"
    return "MEDIUM"


def _iter_line_blocks(revision: SourceRevision) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    ordinal = 0
    for chapter in revision.chapters:
        offset = 0
        for raw in chapter.canonical_text.splitlines(keepends=True):
            line = raw.rstrip("\r\n")
            line_end = offset + len(line)
            if line.strip():
                span_ids = tuple(
                    span.id for span in chapter.spans
                    if span.start_offset < line_end and span.end_offset > offset
                )
                normalized = normalize_block_text(line)
                blocks.append(DocumentBlock(
                    id=f"ab:db:{text_hash(f'{revision.id}:{chapter.id}:{offset}:{line_end}:{line}')}",
                    chapter_id=chapter.id,
                    ordinal=ordinal,
                    start_offset=offset,
                    end_offset=line_end,
                    source_span_ids=span_ids,
                    original_text=line,
                    normalized_text=normalized,
                    content_role="unknown",
                    confidence=0.0,
                    provenance=(),
                    recurrence_group=None,
                    structure_quality=_quality(revision.source_format),
                ))
                ordinal += 1
            offset += len(raw)
        if offset < len(chapter.canonical_text):
            line = chapter.canonical_text[offset:]
            if line.strip():
                line_end = len(chapter.canonical_text)
                span_ids = tuple(
                    span.id for span in chapter.spans
                    if span.start_offset < line_end and span.end_offset > offset
                )
                blocks.append(DocumentBlock(
                    id=f"ab:db:{text_hash(f'{revision.id}:{chapter.id}:{offset}:{line_end}:{line}')}",
                    chapter_id=chapter.id, ordinal=ordinal,
                    start_offset=offset, end_offset=line_end,
                    source_span_ids=span_ids, original_text=line,
                    normalized_text=normalize_block_text(line),
                    content_role="unknown", confidence=0.0, provenance=(),
                    recurrence_group=None, structure_quality=_quality(revision.source_format),
                ))
                ordinal += 1
    return blocks


def _pdf_edge_evidence(metadata: Mapping[str, Any]) -> tuple[Counter[str], Counter[str]]:
    top: Counter[str] = Counter()
    bottom: Counter[str] = Counter()
    pages = metadata.get("pdf_page_edges")
    if not isinstance(pages, list):
        return top, bottom
    for page in pages:
        if not isinstance(page, dict):
            continue
        for value in page.get("top", []) if isinstance(page.get("top"), list) else []:
            normalized = normalize_block_text(str(value))
            if normalized:
                top[normalized] += 1
        for value in page.get("bottom", []) if isinstance(page.get("bottom"), list) else []:
            normalized = normalize_block_text(str(value))
            if normalized:
                bottom[normalized] += 1
    return top, bottom


def _evidence(source: str, signal: str, value: Any) -> dict[str, Any]:
    return {"source": source, "signal": signal, "value": value}


def _with_role(
    block: DocumentBlock, role: str, confidence: float,
    *evidence: dict[str, Any],
) -> DocumentBlock:
    if role not in CONTENT_ROLES:
        role = "unknown"
    return replace(
        block, content_role=role, confidence=max(0.0, min(1.0, confidence)),
        provenance=tuple((*block.provenance, *evidence)),
    )


def _is_body_like(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) >= 100:
        return True
    words = stripped.split()
    return len(words) >= 14 and stripped[-1:] in {".", "!", "?", "”", '"', "’"}


def _all_caps_heading(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and len(text.strip()) <= 80 and all(char.isupper() for char in letters)


def _initial_roles(
    revision: SourceRevision, blocks: list[DocumentBlock],
) -> list[DocumentBlock]:
    counts = Counter(block.normalized_text for block in blocks if block.normalized_text)
    top_edges, bottom_edges = _pdf_edge_evidence(revision.metadata)
    title = normalize_block_text(str(revision.metadata.get("title") or ""))
    chapter_titles = {
        chapter.id: normalize_block_text(chapter.title)
        for chapter in revision.chapters
        if chapter.title and chapter.title != "Opening"
    }
    creator = normalize_block_text(str(
        revision.metadata.get("creator") or revision.metadata.get("author") or ""
    ))
    seen_title = False
    optional_region: str | None = None
    toc_region = False
    result: list[DocumentBlock] = []

    optional_headings = {
        "dedication": "dedication",
        "epigraph": "epigraph",
        "foreword": "foreword",
        "preface": "preface",
        "author's note": "author_note",
        "authors note": "author_note",
        "author note": "author_note",
        "acknowledgements": "acknowledgements",
        "acknowledgments": "acknowledgements",
        "endnotes": "endnote",
        "notes": "endnote",
    }

    for index, block in enumerate(blocks):
        text = block.original_text.strip()
        normalized = block.normalized_text
        recurrence = None
        if normalized and counts[normalized] >= 2 and len(normalized) <= 120:
            recurrence = f"ab:rg:{text_hash(normalized)}"
            block = replace(block, recurrence_group=recurrence)

        chapter_changed = (
            index == 0 or blocks[index - 1].chapter_id != block.chapter_id
        )
        if chapter_changed:
            optional_region = None
            toc_region = False

        role: DocumentBlock | None = None

        # Strong source/document identity evidence.
        if (
            chapter_titles.get(block.chapter_id)
            and normalized == chapter_titles[block.chapter_id]
        ):
            role = _with_role(
                block, "chapter_heading", 0.999,
                _evidence("source_semantic", "chapter_title_match", True),
            )
        elif title and normalized == title and not seen_title:
            seen_title = True
            role = _with_role(
                block, "book_title", 0.995,
                _evidence("source_metadata", "title_match", True),
            )
        elif creator and normalized == creator and index < 12:
            role = _with_role(
                block, "author_name", 0.99,
                _evidence("source_metadata", "creator_match", True),
            )

        # PDF edge recurrence outranks lexical ambiguity.
        top_count = top_edges[normalized]
        bottom_count = bottom_edges[normalized]
        if role is None and len(normalized) <= 120 and max(top_count, bottom_count) >= 2:
            if _PAGE.fullmatch(text) or text.isdigit():
                role = _with_role(
                    block, "page_number", 0.999,
                    _evidence("pdf_layout", "page_edge_recurrence", max(top_count, bottom_count)),
                )
            else:
                edge_role = "running_header" if top_count >= bottom_count else "running_footer"
                role = _with_role(
                    block, edge_role, 0.997,
                    _evidence("repetition", "same_normalized_text_page_count", max(top_count, bottom_count)),
                    _evidence("pdf_layout", "edge", "top" if top_count >= bottom_count else "bottom"),
                )

        if role is None and _PAGE.fullmatch(text):
            role = _with_role(block, "page_number", 0.995, _evidence("pattern", "page_number", text))
        elif role is None and _ISBN.search(text):
            role = _with_role(block, "isbn", 0.999, _evidence("pattern", "isbn", True))
        elif role is None and _COPYRIGHT.search(text):
            role = _with_role(block, "copyright", 0.995, _evidence("pattern", "copyright", True))
        elif role is None and normalized in {"contents", "table of contents"}:
            toc_region = True
            role = _with_role(block, "table_of_contents", 0.999, _evidence("sequence_rule", "toc_heading", True))
        elif role is None and normalized in {"bibliography", "references"}:
            optional_region = "bibliography"
            role = _with_role(block, "bibliography", 0.99, _evidence("sequence_rule", "section_heading", normalized))
        elif role is None and normalized == "index":
            optional_region = "index"
            role = _with_role(block, "index", 0.99, _evidence("sequence_rule", "section_heading", normalized))
        elif role is None and normalized in optional_headings:
            optional_region = optional_headings[normalized]
            role = _with_role(block, optional_region, 0.99, _evidence("sequence_rule", "optional_section_heading", normalized))
        elif role is None and _CHAPTER.fullmatch(text):
            toc_region = False
            optional_region = None
            role = _with_role(block, "chapter_heading", 0.995, _evidence("pattern", "chapter_heading", True))
        elif role is None and _PART.fullmatch(text):
            toc_region = False
            optional_region = None
            role = _with_role(block, "part_heading", 0.995, _evidence("pattern", "part_heading", True))
        elif role is None and normalized == "prologue":
            toc_region = False
            optional_region = None
            role = _with_role(block, "prologue_heading", 0.995, _evidence("pattern", "prologue", True))
        elif role is None and normalized == "epilogue":
            toc_region = False
            optional_region = None
            role = _with_role(block, "epilogue_heading", 0.995, _evidence("pattern", "epilogue", True))
        elif role is None and _SCENE_BREAK.fullmatch(text):
            role = _with_role(block, "scene_break", 0.995, _evidence("pattern", "scene_break", text))
        elif role is None and _FOOTNOTE_MARKER.fullmatch(text):
            role = _with_role(block, "footnote_marker", 0.97, _evidence("pattern", "footnote_marker", True))
        elif role is None and _FOOTNOTE_BODY.match(text):
            role = _with_role(block, "footnote_body", 0.9, _evidence("pattern", "footnote_body", True))

        if role is None and toc_region:
            if _TOC_ENTRY.search(text) or _CHAPTER.fullmatch(text) or _PART.fullmatch(text):
                role = _with_role(block, "table_of_contents", 0.98, _evidence("sequence_rule", "inside_toc_region", True))
            elif _is_body_like(text):
                toc_region = False
            else:
                role = _with_role(block, "table_of_contents", 0.82, _evidence("sequence_rule", "inside_toc_region", True))

        if role is None and optional_region:
            if optional_region in {"bibliography", "index"}:
                role = _with_role(block, optional_region, 0.9, _evidence("sequence_rule", "inside_section", optional_region))
            elif not _CHAPTER.fullmatch(text) and normalized not in {"prologue", "epilogue"}:
                role = _with_role(block, optional_region, 0.9, _evidence("sequence_rule", "inside_optional_section", optional_region))
            else:
                optional_region = None

        if role is None and _is_body_like(text):
            role = _with_role(block, "story_text", 0.99, _evidence("pattern", "body_prose", True))
        elif role is None and len(text) > 80:
            role = _with_role(block, "story_text", 0.95, _evidence("pattern", "long_text", len(text)))
        elif role is None and _all_caps_heading(text) and counts[normalized] == 1:
            # Short all-caps lines may be scene/location headings. Keep them
            # analysis-visible and spoken in Standard mode; ambiguity remains explicit.
            role = _with_role(block, "scene_heading", 0.72, _evidence("pattern", "short_all_caps_heading", True))
        elif role is None:
            # Fail open. UNKNOWN is read and visible unless AI or a user override
            # supplies stronger structure evidence.
            role = _with_role(block, "unknown", 0.45, _evidence("deterministic", "insufficient_evidence", True))

        result.append(role)
    return result


def _ambiguous_regions(blocks: Sequence[DocumentBlock]) -> list[list[DocumentBlock]]:
    regions: list[list[DocumentBlock]] = []
    current: list[DocumentBlock] = []
    previous_ordinal: int | None = None
    previous_chapter: str | None = None
    for block in blocks:
        ambiguous = block.content_role == "unknown" or block.confidence < 0.70
        contiguous = (
            previous_ordinal is not None
            and block.ordinal == previous_ordinal + 1
            and block.chapter_id == previous_chapter
        )
        if ambiguous:
            if current and not contiguous:
                regions.append(current)
                current = []
            current.append(block)
        elif current:
            regions.append(current)
            current = []
        previous_ordinal = block.ordinal
        previous_chapter = block.chapter_id
    if current:
        regions.append(current)
    return regions


def _parse_ai_result(raw: object, expected: set[str]) -> dict[str, tuple[str, float]]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict) or not isinstance(raw.get("blocks"), list):
        raise ValueError("document structure classifier must return blocks")
    parsed: dict[str, tuple[str, float]] = {}
    for item in raw["blocks"]:
        if not isinstance(item, dict):
            continue
        block_id = item.get("block_id")
        role = item.get("content_role")
        confidence = item.get("confidence")
        if (
            isinstance(block_id, str) and block_id in expected
            and isinstance(role, str) and role in CONTENT_ROLES
            and isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        ):
            parsed[block_id] = (role, max(0.0, min(1.0, float(confidence))))
    return parsed


def analyze_document_structure(
    revision: SourceRevision,
    *, region_classifier: Callable[[dict[str, Any]], object] | None = None,
) -> DocumentStructureAnalysis:
    """Classify document blocks deterministically, with optional region AI fallback."""
    blocks = _initial_roles(revision, _iter_line_blocks(revision))
    ai_used = False
    if region_classifier is not None:
        by_ordinal = {block.ordinal: block for block in blocks}
        replacements: dict[str, DocumentBlock] = {}
        for region in _ambiguous_regions(blocks):
            first, last = region[0], region[-1]
            previous = by_ordinal.get(first.ordinal - 1)
            following = by_ordinal.get(last.ordinal + 1)
            payload = {
                "task": "classify_ambiguous_document_region",
                "version": DOCUMENT_STRUCTURE_VERSION,
                "source_format": revision.source_format,
                "allowed_roles": sorted(CONTENT_ROLES),
                "instruction": (
                    "Classify only the supplied ambiguous blocks. UNKNOWN is valid. "
                    "Do not rewrite source text. Return JSON with key blocks; each item "
                    "must contain block_id, content_role, confidence."
                ),
                "previous": previous.original_text if previous and previous.chapter_id == first.chapter_id else None,
                "region": [{"block_id": item.id, "text": item.original_text} for item in region],
                "next": following.original_text if following and following.chapter_id == first.chapter_id else None,
            }
            try:
                parsed = _parse_ai_result(
                    region_classifier(payload), {item.id for item in region}
                )
            except Exception:
                continue
            for item in region:
                result = parsed.get(item.id)
                if result is None:
                    continue
                role, confidence = result
                if role == "unknown":
                    continue
                replacements[item.id] = _with_role(
                    item, role, confidence,
                    _evidence("ai_fallback", "ambiguous_region", True),
                )
                ai_used = True
        blocks = [replacements.get(block.id, block) for block in blocks]
    return DocumentStructureAnalysis(
        source_revision_id=revision.id,
        version=DOCUMENT_STRUCTURE_VERSION,
        blocks=tuple(blocks),
        ai_fallback_used=ai_used,
    )


def render_policy(role: str, mode: str = "standard") -> str:
    """Derive speech behavior from role and audiobook mode."""
    mode = (mode or "standard").strip().casefold()
    if mode == "verbatim":
        return READ
    if role in NON_STORY_ROLES:
        return SKIP
    if role == "scene_break":
        return SKIP
    if mode == "story_only":
        return READ if role in {"story_text", "scene_heading", "unknown"} else SKIP
    if role in {"book_title"}:
        return READ_ONCE
    if role in STORY_STRUCTURE_ROLES or role in {"story_text", "scene_heading", "unknown"}:
        return READ
    if role in OPTIONAL_ROLES or role in {"subtitle", "author_name"}:
        return SKIP
    return READ


def analysis_policy(role: str, consumer: str) -> str:
    """Derive visibility per downstream consumer rather than persisting it."""
    consumer = (consumer or "speaker_attribution").strip().casefold()
    if role in NON_STORY_ROLES:
        return EXCLUDE
    if consumer == "chapter_summarizer":
        return INCLUDE if role != "footnote_marker" else EXCLUDE
    if consumer in {"dialogue_pronunciation", "pronunciation"}:
        return INCLUDE if role in {"story_text", "unknown"} else EXCLUDE
    if consumer == "speaker_attribution":
        if role in {"story_text", "unknown"}:
            return INCLUDE
        if role in STORY_STRUCTURE_ROLES or role in {"scene_heading", "scene_break"}:
            return CONTEXT_ONLY
        if role in OPTIONAL_ROLES:
            return CONTEXT_ONLY
        return EXCLUDE
    return INCLUDE


def _override_rank(scope: str) -> int:
    return {
        "BLOCK": 4, "REGION": 3, "RECURRENCE_GROUP": 3, "DOCUMENT_ROLE": 2,
    }.get(scope, 0)


def _matching_overrides(
    block: DocumentBlock, overrides: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    matches: list[Mapping[str, Any]] = []
    for item in overrides:
        scope = str(item.get("scope") or "").upper()
        key = str(item.get("scope_key") or "")
        if (
            (scope == "BLOCK" and key == block.id)
            or (scope == "RECURRENCE_GROUP" and block.recurrence_group and key == block.recurrence_group)
            or (scope == "DOCUMENT_ROLE" and key == block.content_role)
        ):
            matches.append(item)
    matches.sort(key=lambda item: (
        _override_rank(str(item.get("scope") or "").upper()),
        int(item.get("revision") or 0),
    ), reverse=True)
    return matches


def effective_role(
    block: DocumentBlock, overrides: Sequence[Mapping[str, Any]] = (),
) -> str:
    for item in _matching_overrides(block, overrides):
        role = str(item.get("role_override") or "")
        if role in CONTENT_ROLES:
            return role
    return block.content_role


def effective_render_action(
    block: DocumentBlock, *, mode: str,
    overrides: Sequence[Mapping[str, Any]] = (),
) -> str:
    for item in _matching_overrides(block, overrides):
        action = str(item.get("action") or "DEFAULT").upper()
        if action in {READ, SKIP, READ_ONCE}:
            return action
        if action == "DEFAULT":
            break
    return render_policy(effective_role(block, overrides), mode)


def mask_span_for_analysis(
    span: SourceSpan, blocks: Sequence[DocumentBlock], *,
    consumer: str = "speaker_attribution",
    overrides: Sequence[Mapping[str, Any]] = (),
) -> SourceSpan:
    """Blank excluded block ranges while preserving span identity and offsets."""
    chars = list(span.source_text)
    for block in blocks:
        if block.chapter_id != span.chapter_id:
            continue
        if analysis_policy(effective_role(block, overrides), consumer) != EXCLUDE:
            continue
        start = max(span.start_offset, block.start_offset)
        end = min(span.end_offset, block.end_offset)
        if start >= end:
            continue
        for absolute in range(start, end):
            relative = absolute - span.start_offset
            if 0 <= relative < len(chars) and chars[relative] not in {"\n", "\r"}:
                chars[relative] = " "
    return replace(span, source_text="".join(chars))


def mask_span_for_render(
    span: SourceSpan, blocks: Sequence[DocumentBlock], *, mode: str = "standard",
    overrides: Sequence[Mapping[str, Any]] = (),
    read_once_block_ids: set[str] | None = None,
) -> str:
    """Return a derived speech view; canonical SourceSpan text remains untouched."""
    chars = list(span.source_text)
    for block in blocks:
        if block.chapter_id != span.chapter_id:
            continue
        action = effective_render_action(block, mode=mode, overrides=overrides)
        if action == READ_ONCE:
            if read_once_block_ids is not None and block.id not in read_once_block_ids:
                action = SKIP
        if action != SKIP:
            continue
        start = max(span.start_offset, block.start_offset)
        end = min(span.end_offset, block.end_offset)
        if start >= end:
            continue
        for absolute in range(start, end):
            relative = absolute - span.start_offset
            if 0 <= relative < len(chars) and chars[relative] not in {"\n", "\r"}:
                chars[relative] = " "
    return "".join(chars)
