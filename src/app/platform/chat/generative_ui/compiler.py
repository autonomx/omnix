"""Compile a finished reply's ```omnix-ui fences into ``metadata.ui`` (roadmap §6.3).

``compile_chat_ui`` is pure: the same content and scope (clock, bound sources,
validated market symbols) always give the same payload for one
``COMPILER_VERSION``. It returns ``None`` when the reply has no ``omnix-ui``
fence, so ordinary replies are stored exactly as before.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from .catalog import (
    BLOCK_ID,
    CATALOG,
    MAX_BLOCK_BYTES,
    MAX_BLOCKS,
    MAX_PAYLOAD_BYTES,
    BlockRejected,
    BoundSource,
    ChatUiDiagnostic,
    ChatUiPayload,
    NormalizeContext,
    Severity,
    best_effort_text,
    fit_chart,
    to_speech,
    to_text,
    validate_block,
)
from .parser import UI_INFO_STRING, Fence, FenceJsonError, parse_fence_json, scan_fences

COMPILER_VERSION = "gui-compiler-1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CompileScope:
    """What a compile may use besides the content; resolvers fill it before the commit."""

    clock: Callable[[], datetime] = utc_now
    # Binding targets for this turn, keyed ``source:<n>`` / ``context:<id>`` (GUI-4.1).
    sources: Mapping[str, BoundSource] = field(default_factory=dict)
    # Market-data symbols validated for this reply; None when no validation ran (GUI-4.2).
    market_symbols: Mapping[str, str] | None = None
    interrupted: bool = False


def has_ui_fence(content: str) -> bool:
    return UI_INFO_STRING in content and bool(scan_fences(content))


def _timestamp(value: datetime) -> str:
    moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class _Compilation:
    def __init__(self, content: str, scope: CompileScope, compiled_at: str) -> None:
        self.content = content
        self.scope = scope
        self.compiled_at = compiled_at
        self.segments: list[dict[str, Any]] = []
        self.blocks: dict[str, dict[str, Any]] = {}
        self.diagnostics: list[ChatUiDiagnostic] = []
        self.used_ids: set[str] = set()
        self.next_ordinal = 1
        self.shown = 0

    def note(self, block: str | None, code: str, severity: Severity, path: str | None = None, detail: str | None = None) -> None:
        self.diagnostics.append(ChatUiDiagnostic(block=block, code=code, path=path, severity=severity, detail=detail))

    def markdown(self, start: int, end: int) -> None:
        if end > start and self.content[start:end].strip():
            self.segments.append({"kind": "markdown", "start": start, "end": end})

    def text(self, value: str) -> None:
        self.segments.append({"kind": "text", "text": value})

    def assign_id(self, raw: Any) -> str:
        candidate = raw.strip() if isinstance(raw, str) else None
        if candidate and BLOCK_ID.match(candidate) and candidate not in self.used_ids:
            self.used_ids.add(candidate)
            return candidate
        while f"b{self.next_ordinal}" in self.used_ids:
            self.next_ordinal += 1
        assigned = f"b{self.next_ordinal}"
        self.used_ids.add(assigned)
        if candidate:
            reason = "duplicate_id" if candidate in self.used_ids else "invalid_id"
            self.note(assigned, reason, "info", "id", candidate[:64])
        return assigned

    def fence(self, fence: Fence) -> None:
        try:
            parsed = parse_fence_json(fence.body)
        except FenceJsonError as error:
            block_id = self.assign_id(None)
            self.note(block_id, "unclosed_fence" if not fence.closed else "invalid_json", "degraded", detail=str(error)[:200])
            self.text("[A block could not be shown.]")
            return
        spec = parsed.value
        block_id = self.assign_id(spec.get("id") if isinstance(spec, dict) else None)
        if parsed.repaired:
            self.note(block_id, "json_repaired", "info")
        block_type = spec.get("type") if isinstance(spec, dict) else None
        block_type = block_type if isinstance(block_type, str) else None
        if not fence.closed:
            self.degrade(block_id, spec, block_type, "unclosed_fence")
            return
        if not isinstance(spec, dict):
            self.degrade(block_id, spec, None, "not_object")
            return
        if block_type is None:
            self.degrade(block_id, spec, None, "missing_type")
            return
        if block_type not in CATALOG:
            self.degrade(block_id, spec, block_type, "unknown_type", detail=block_type[:64])
            return
        if spec.get("v", 1) != 1:
            self.degrade(block_id, spec, block_type, "unsupported_version")
            return
        context = NormalizeContext(
            block_id=block_id,
            compiled_at=self.compiled_at,
            sources=self.scope.sources,
            market_symbols=self.scope.market_symbols,
        )
        try:
            normalized = CATALOG[block_type].normalize(spec, context)
            block = validate_block(
                {
                    "type": block_type,
                    "id": block_id,
                    "v": 1,
                    **normalized,
                    "bindings": [binding.model_dump(exclude_none=True) for binding in context.bindings],
                }
            )
        except BlockRejected as rejected:
            self.diagnostics.extend(context.diagnostics)
            self.degrade(block_id, spec, block_type, rejected.code, rejected.path, rejected.detail)
            return
        except ValidationError as error:
            self.diagnostics.extend(context.diagnostics)
            self.degrade(block_id, spec, block_type, "invalid_block", detail=str(error.errors()[0].get("msg", ""))[:200])
            return
        self.diagnostics.extend(context.diagnostics)
        if self.shown >= MAX_BLOCKS:
            self.note(block_id, "too_many_blocks", "degraded", detail=f"at most {MAX_BLOCKS} blocks per reply")
            self.text(to_text(block))
            return
        if _size(block) > MAX_BLOCK_BYTES and block["type"] == "chart":
            cap = fit_chart(block, MAX_BLOCK_BYTES, _size)
            if cap is not None:
                self.note(block_id, "downsampled", "info", "series", f"at most {cap} points per series to fit {MAX_BLOCK_BYTES} bytes")
        if _size(block) > MAX_BLOCK_BYTES:
            self.note(block_id, "block_too_large", "degraded", detail=f"over {MAX_BLOCK_BYTES} bytes")
            self.text(to_text(block))
            return
        self.shown += 1
        self.blocks[block_id] = block
        self.segments.append({"kind": "block", "id": block_id})

    def degrade(
        self,
        block_id: str,
        spec: Any,
        block_type: str | None,
        code: str,
        path: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.note(block_id, code, "degraded", path, detail)
        self.text(best_effort_text(spec, block_type))

    def shrink_to_cap(self) -> None:
        """Turn the largest blocks into text until the payload fits (roadmap §7.3)."""
        while self.blocks and _size(self.payload()) > MAX_PAYLOAD_BYTES:
            largest = max(self.blocks, key=lambda key: (_size(self.blocks[key]), key))
            block = self.blocks.pop(largest)
            index = next(i for i, segment in enumerate(self.segments) if segment.get("id") == largest)
            self.segments[index] = {"kind": "text", "text": to_text(block)}
            self.note(largest, "payload_too_large", "degraded", detail=f"metadata.ui over {MAX_PAYLOAD_BYTES} bytes")

    def projections(self) -> tuple[str, str]:
        texts: list[str] = []
        speeches: list[str] = []
        for segment in self.segments:
            if segment["kind"] == "markdown":
                span = self.content[segment["start"] : segment["end"]]
                texts.append(span.strip())
                speeches.append(markdown_to_speech(span))
            elif segment["kind"] == "block":
                block = self.blocks[segment["id"]]
                texts.append(to_text(block))
                speeches.append(to_speech(block))
            else:
                texts.append(segment["text"])
                speeches.append(segment["text"])
        return "\n\n".join(item for item in texts if item), "\n\n".join(item for item in speeches if item.strip())

    def payload(self) -> dict[str, Any]:
        text, speech = self.projections()
        return {
            "version": 1,
            "compiler_version": COMPILER_VERSION,
            "compiled_at": self.compiled_at,
            "segments": self.segments,
            "blocks": self.blocks,
            "text": text,
            "speech": speech,
            "diagnostics": [item.model_dump(exclude_none=True) for item in self.diagnostics],
        }


class PayloadTooLarge(ValueError):
    """The reply's prose alone exceeds the ``metadata.ui`` cap."""


def compile_chat_ui(content: str, scope: CompileScope | None = None) -> dict[str, Any] | None:
    """Compile ``content`` into a ``metadata.ui`` payload, or None when it has no ```omnix-ui fence."""
    scope = scope or CompileScope()
    if scope.interrupted or UI_INFO_STRING not in content:
        return None
    fences = scan_fences(content)
    if not fences:
        return None
    compilation = _Compilation(content, scope, _timestamp(scope.clock()))
    cursor = 0
    for fence in fences:
        compilation.markdown(cursor, fence.start)
        compilation.fence(fence)
        cursor = fence.end
    compilation.markdown(cursor, len(content))
    compilation.shrink_to_cap()
    payload = compilation.payload()
    if _size(payload) > MAX_PAYLOAD_BYTES:
        raise PayloadTooLarge(f"metadata.ui over {MAX_PAYLOAD_BYTES} bytes without blocks")
    ChatUiPayload.model_validate(payload)
    return payload


def rebase_ui_after_rewrite(ui: Mapping[str, Any], old_content: str, new_content: str) -> dict[str, Any] | None:
    """Keep ``metadata.ui`` valid when a later step appends to the stored content.

    Research citation validation and release notices append to a committed
    reply. An appended tail becomes one more Markdown span; any other rewrite
    invalidates the offsets, so the payload is dropped (None).
    """
    if new_content == old_content:
        return dict(ui)
    if not new_content.startswith(old_content):
        return None
    tail = new_content[len(old_content) :]
    rebased = dict(ui)
    segments = list(rebased.get("segments") or [])
    if tail.strip():
        segments.append({"kind": "markdown", "start": len(old_content), "end": len(new_content)})
        rebased["text"] = "\n\n".join(item for item in (str(ui.get("text") or ""), tail.strip()) if item)
        rebased["speech"] = "\n\n".join(item for item in (str(ui.get("speech") or ""), markdown_to_speech(tail)) if item.strip())
    rebased["segments"] = segments
    return rebased


def rebase_reply_ui(metadata: dict[str, Any], old_content: str, new_content: str) -> None:
    """Rebase ``metadata["ui"]`` in place after a content rewrite; drop it, with ``ui_error``, if offsets broke."""
    ui = metadata.get("ui")
    if not isinstance(ui, Mapping):
        return
    rebased = rebase_ui_after_rewrite(ui, old_content, new_content)
    if rebased is None:
        metadata.pop("ui", None)
        metadata["ui_error"] = {"code": "content_rewritten"}
    else:
        metadata["ui"] = rebased


_TABLE_DELIMITER =re.compile(r"^\s{0,3}\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
_ALERT = re.compile(r"^\s{0,3}>\s?\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$", re.I)
_FENCE_LINE = re.compile(r"^\s{0,3}```")


def markdown_to_speech(markdown: str) -> str:
    """Prose for audio: Markdown markers removed, tables and code summarized, citations dropped."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    spoken: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _FENCE_LINE.match(line):
            index += 1
            while index < len(lines) and not re.match(r"^\s{0,3}```\s*$", lines[index]):
                index += 1
            index += 1
            spoken.append("There is a code block in the written reply.")
            continue
        if "|" in line and index + 1 < len(lines) and _TABLE_DELIMITER.match(lines[index + 1]) and "|" in lines[index + 1]:
            index += 2
            rows = 0
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows += 1
                index += 1
            spoken.append(f"There is a table with {rows} row{'' if rows == 1 else 's'} in the written reply.")
            continue
        alert = _ALERT.match(line)
        if alert:
            spoken.append(f"{alert.group(1).capitalize()}:")
            index += 1
            continue
        text = re.sub(r"^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)", "", line)
        text = re.sub(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$", "", text)
        text = re.sub(r"\[([^\]]+)\]\((?:[^)]+)\)", r"\1", text)
        text = re.sub(r"\s?\[S\d+\]", "", text, flags=re.I)
        text = re.sub(r"(\*\*|__|`)", "", text)
        text = re.sub(r"(?<!\w)[*_](\S(?:.*?\S)?)[*_](?!\w)", r"\1", text)
        if text.strip():
            spoken.append(text.strip())
        index += 1
    return "\n".join(spoken)
