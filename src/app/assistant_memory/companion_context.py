"""Deterministic, bounded companion context for low-latency live generation."""
from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.chat.context_budget import estimate_tokens
from app.chat.prompt_assembly import PromptMemoryItem

CompanionSection = Literal[
    "stable_profile",
    "communication_preferences",
    "relationship_context",
    "due_routines",
    "open_loops",
    "active_goals",
    "recent_episodes",
    "query_relevant_memories",
    "capability_context",
]

_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}")
_CATEGORY_SECTION: dict[str, CompanionSection] = {
    "instruction": "communication_preferences",
    "preference": "communication_preferences",
    "relationship": "relationship_context",
    "project": "active_goals",
    "fact": "stable_profile",
}
_CATEGORY_BASE = {
    "instruction": 500,
    "preference": 450,
    "relationship": 425,
    "project": 375,
    "fact": 325,
}
_SCOPE_BASE = {"session": 80, "project": 60, "workspace": 40, "global": 20}
_SECTION_ORDER: tuple[CompanionSection, ...] = (
    "communication_preferences",
    "relationship_context",
    "active_goals",
    "stable_profile",
    "due_routines",
    "open_loops",
    "recent_episodes",
    "query_relevant_memories",
    "capability_context",
)


class CompanionContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    content: str
    section: CompanionSection
    selection_reason: str
    activation_score: int
    source_revision: int = Field(ge=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    expires_at: str | None = None
    last_surfaced_at: str | None = None
    prompt_item: PromptMemoryItem


class CompanionContextPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    owner_type: str
    owner_id: str
    snapshot_id: str | None = None
    snapshot_revision: int | None = None
    token_budget: int = Field(ge=0)
    token_estimate: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    truncated: bool = False
    cache_hit: bool = False
    build_ms: float = Field(ge=0.0)
    sections: dict[CompanionSection, tuple[CompanionContextItem, ...]]

    @property
    def prompt_memory(self) -> list[PromptMemoryItem]:
        result: list[PromptMemoryItem] = []
        for section in _SECTION_ORDER:
            result.extend(item.prompt_item for item in self.sections.get(section, ()))
        return result

    def content_free_diagnostics(self) -> dict[str, Any]:
        return {
            "packet_version": 1,
            "snapshot_id": self.snapshot_id,
            "snapshot_revision": self.snapshot_revision,
            "token_budget": self.token_budget,
            "token_estimate": self.token_estimate,
            "selected_count": self.selected_count,
            "candidate_count": self.candidate_count,
            "truncated": self.truncated,
            "cache_hit": self.cache_hit,
            "build_ms": round(self.build_ms, 3),
            "section_counts": {
                section: len(items) for section, items in self.sections.items()
            },
            "selected_memory_ids": [
                item.memory_id
                for section in _SECTION_ORDER
                for item in self.sections.get(section, ())
            ],
            "selection_reasons": [
                item.selection_reason
                for section in _SECTION_ORDER
                for item in self.sections.get(section, ())
            ],
        }


@dataclass(frozen=True, slots=True)
class _CachedBaseline:
    items: tuple[CompanionContextItem, ...]
    candidate_count: int


_cache_lock = threading.RLock()
_baseline_cache: dict[str, _CachedBaseline] = {}
_MAX_CACHE_ENTRIES = 512


def invalidate_companion_context(session_id: str | None = None) -> None:
    """Invalidate derived packets without touching authoritative memory."""

    with _cache_lock:
        if session_id is None:
            _baseline_cache.clear()
            return
        prefix = session_id + "\x1f"
        for key in [candidate for candidate in _baseline_cache if candidate.startswith(prefix)]:
            _baseline_cache.pop(key, None)


def _session_identity(session: Any) -> tuple[str, str, str]:
    session_id = str(getattr(session, "id", "") or "unknown-session")
    interaction_mode = str(getattr(session, "interaction_mode", "system") or "system")
    character_id = str(getattr(session, "character_id", "") or "")
    if interaction_mode == "character" and character_id:
        return session_id, "character", character_id
    return session_id, "system", "system-assistant"


def _snapshot_identity(session: Any) -> tuple[str | None, int | None]:
    snapshot_id = str(getattr(session, "memory_snapshot_id", "") or "") or None
    revision = getattr(session, "memory_snapshot_revision", None)
    try:
        parsed_revision = int(revision) if revision is not None else None
    except (TypeError, ValueError):
        parsed_revision = None
    return snapshot_id, parsed_revision


def _cache_key(session: Any, approved_memory: list[PromptMemoryItem]) -> str:
    session_id, owner_type, owner_id = _session_identity(session)
    snapshot_id, snapshot_revision = _snapshot_identity(session)
    signature = hashlib.sha256(
        "\n".join(
            f"{item.memory_id}:{item.revision}:{item.source}:{item.scope}:{item.category}"
            for item in approved_memory
        ).encode("utf-8")
    ).hexdigest()[:20]
    return "\x1f".join(
        [
            session_id,
            owner_type,
            owner_id,
            snapshot_id or "none",
            str(snapshot_revision or 0),
            signature,
        ]
    )


def _terms(value: str) -> frozenset[str]:
    return frozenset(term.casefold() for term in _TERM_PATTERN.findall(value))


def _section(item: PromptMemoryItem) -> CompanionSection:
    return _CATEGORY_SECTION.get(item.category, "stable_profile")


def _baseline_item(item: PromptMemoryItem) -> CompanionContextItem:
    section = _section(item)
    score = (
        _CATEGORY_BASE.get(item.category, 250)
        + _SCOPE_BASE.get(item.scope, 0)
        + (10 if item.source == "character" else 5 if item.source == "shared_system" else 0)
    )
    return CompanionContextItem(
        memory_id=item.memory_id,
        content=item.content,
        section=section,
        selection_reason=f"approved_{section}",
        activation_score=score,
        source_revision=item.revision,
        prompt_item=item,
    )


def _baseline(session: Any, approved_memory: list[PromptMemoryItem]) -> tuple[_CachedBaseline, bool]:
    key = _cache_key(session, approved_memory)
    with _cache_lock:
        cached = _baseline_cache.get(key)
        if cached is not None:
            return cached, True
    values = tuple(
        sorted(
            (_baseline_item(item) for item in approved_memory),
            key=lambda item: (
                -item.activation_score,
                item.section,
                item.memory_id,
            ),
        )
    )
    baseline = _CachedBaseline(items=values, candidate_count=len(approved_memory))
    with _cache_lock:
        if len(_baseline_cache) >= _MAX_CACHE_ENTRIES:
            _baseline_cache.pop(next(iter(_baseline_cache)))
        _baseline_cache[key] = baseline
    return baseline, False


def _query_score(item: CompanionContextItem, query_terms: frozenset[str]) -> tuple[int, str]:
    if not query_terms:
        return item.activation_score, item.selection_reason
    overlap = len(query_terms & _terms(item.content))
    if not overlap:
        return item.activation_score, item.selection_reason
    return item.activation_score + overlap * 175, "current_turn_term_overlap"


def build_companion_context_packet(
    session: Any,
    user_message: Any,
    approved_memory: list[PromptMemoryItem],
    *,
    token_budget: int = 1_000,
) -> CompanionContextPacket:
    """Select a bounded packet without transcript or history scans."""

    started = time.perf_counter()
    budget = max(0, int(token_budget))
    baseline, cache_hit = _baseline(session, approved_memory)
    query_terms = _terms(str(getattr(user_message, "content", "") or ""))
    scored: list[CompanionContextItem] = []
    for item in baseline.items:
        score, reason = _query_score(item, query_terms)
        scored.append(
            item.model_copy(
                update={"activation_score": score, "selection_reason": reason}
            )
        )
    scored.sort(
        key=lambda item: (
            -item.activation_score,
            _SECTION_ORDER.index(item.section),
            item.memory_id,
        )
    )

    selected: list[CompanionContextItem] = []
    used_tokens = 0
    for item in scored:
        cost = estimate_tokens(item.content) + 8
        if used_tokens + cost > budget:
            continue
        selected.append(item)
        used_tokens += cost

    grouped: dict[CompanionSection, list[CompanionContextItem]] = defaultdict(list)
    for item in selected:
        grouped[item.section].append(item)
    sections: dict[CompanionSection, tuple[CompanionContextItem, ...]] = {
        section: tuple(grouped.get(section, ())) for section in _SECTION_ORDER
    }
    session_id, owner_type, owner_id = _session_identity(session)
    snapshot_id, snapshot_revision = _snapshot_identity(session)
    return CompanionContextPacket(
        session_id=session_id,
        owner_type=owner_type,
        owner_id=owner_id,
        snapshot_id=snapshot_id,
        snapshot_revision=snapshot_revision,
        token_budget=budget,
        token_estimate=used_tokens,
        selected_count=len(selected),
        candidate_count=baseline.candidate_count,
        truncated=len(selected) < baseline.candidate_count,
        cache_hit=cache_hit,
        build_ms=(time.perf_counter() - started) * 1000.0,
        sections=sections,
    )


__all__ = [
    "CompanionContextItem",
    "CompanionContextPacket",
    "build_companion_context_packet",
    "invalidate_companion_context",
]
