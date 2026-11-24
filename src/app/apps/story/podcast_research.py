"""Research for a podcast episode: one web search on the topic, returned as source notes with their links.

The producer asks for it before the script is written. The notes land in the episode's Source notes, where the
producer reads and edits them; the script job then takes them as fenced data like notes typed by hand
(``podcast_script.sources_block``). Nothing here runs while the script is written, so a re-run uses the same facts.

The search is research's quick search (``app.platform.research.contracts``) under research's own settings and
release policy. Without the research feature, or with quick search switched off, there are no notes and the reply
says why.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, Literal

from pydantic import BaseModel, Field

from .podcast_script import SOURCE_LIMIT

# The search query: the title and the start of the brief, cut at a word.
QUERY_CHARS = 200
# Research notes leave room in the episode's source notes for the producer's own.
NOTES_LIMIT = SOURCE_LIMIT * 3 // 4
SOURCE_CHARS = 1200
# Results asked for when research's own settings are not in play (tests); research's settings say otherwise.
DEFAULT_RESULTS = 5
# Quick search's release cohort for podcast research; one cohort for every producer.
RESEARCH_IDENTITY = "podcast"

ResearchStatus = Literal["ok", "empty", "unavailable", "failed"]


class PodcastResearchRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    brief: str = Field(default="", max_length=4000)


class PodcastResearchSource(BaseModel):
    title: str
    url: str | None = None


class PodcastResearchResponse(BaseModel):
    status: ResearchStatus
    message: str
    query: str = ""
    notes: str = ""
    sources: list[PodcastResearchSource] = Field(default_factory=list)
    provider: str | None = None


SearchFactory = Callable[[], Any]


def research_podcast_topic(
    request: PodcastResearchRequest, *, search_factory: SearchFactory | None = None,
) -> PodcastResearchResponse:
    """Source notes for the episode from one quick search; ``search_factory`` gives a service with research's
    ``QuickSearchService.search`` (tests pass a fake, and then the feature and release checks are skipped)."""
    query = research_query(request.title, request.brief)
    if not query:
        return PodcastResearchResponse(status="empty", message="Give the episode a title or a brief to research.")
    max_results = DEFAULT_RESULTS
    if search_factory is None:
        settings, unavailable = _research_settings()
        if unavailable:
            return PodcastResearchResponse(status="unavailable", message=unavailable, query=query)
        max_results = settings.max_results
        search_factory = partial(_quick_search, settings)
    execution = search_factory().search(query, max_results, identity=RESEARCH_IDENTITY)
    diagnostics = getattr(execution, "diagnostics", {}) or {}
    provider = str(diagnostics.get("provider") or "") or None
    if diagnostics.get("status") == "failed":
        return PodcastResearchResponse(
            status="failed", query=query, provider=provider,
            message="The web search did not answer. Try again, or check the research provider in Settings.",
        )
    notes, sources = source_notes(getattr(execution, "items", []) or [])
    if not sources:
        return PodcastResearchResponse(
            status="empty", query=query, provider=provider, message="The web search found nothing on this topic.",
        )
    count = len(sources)
    return PodcastResearchResponse(
        status="ok", query=query, notes=notes, sources=sources, provider=provider,
        message=f"Added notes from {count} web source{'s' if count != 1 else ''}. Check them before you generate.",
    )


def research_query(title: str, brief: str) -> str:
    text = " ".join(f"{title or ''} {brief or ''}".split())
    if len(text) <= QUERY_CHARS:
        return text
    cut = text[:QUERY_CHARS]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def source_notes(items: list[Any]) -> tuple[str, list[PodcastResearchSource]]:
    """A note per search result that has text: its title and link, then its text, until the notes are full."""
    blocks: list[str] = []
    sources: list[PodcastResearchSource] = []
    used = 0
    for item in items:
        title = " ".join(str(_field(item, "title") or "").split()) or "Untitled source"
        url = str(_field(item, "url") or "").strip() or None
        content = " ".join(str(_field(item, "content") or "").split())
        if not content:
            continue
        if len(content) > SOURCE_CHARS:
            content = content[:SOURCE_CHARS].rsplit(" ", 1)[0] + " ..."
        block = f"- {title}{f' ({url})' if url else ''}\n  {content}"
        if used + len(block) > NOTES_LIMIT:
            break
        blocks.append(block)
        sources.append(PodcastResearchSource(title=title, url=url))
        used += len(block) + 2
    if not blocks:
        return "", []
    return "Web research, " + str(len(blocks)) + " sources (check before use):\n\n" + "\n\n".join(blocks), sources


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def _research_enabled() -> bool:
    from app.runtime.config import get_runtime_config
    from app.runtime.feature_catalog import enabled_feature_ids

    return "research" in enabled_feature_ids(get_runtime_config())


def _research_settings() -> tuple[Any, str]:
    """Research's settings, and why quick search may not run now (empty when it may)."""
    if not _research_enabled():
        return None, "Web research is not part of this install."
    from app.platform.research.contracts import (
        load_research_runtime_settings,
        research_release_policy_from_env,
        resolve_research_release,
    )

    settings = load_research_runtime_settings()
    decision = resolve_research_release(
        "quick", settings, research_release_policy_from_env(), identity=RESEARCH_IDENTITY,
    )
    if decision.effective_mode != "quick":
        return settings, f"Web search is switched off ({decision.reason}). Turn on quick research in Settings."
    return settings, ""


def _quick_search(settings: Any) -> Any:
    from app.platform.research.contracts import ProviderFallbackSearchClient, QuickSearchService

    def client_factory(timeout_seconds: float) -> Any:
        return ProviderFallbackSearchClient(providers=settings.effective_provider_chain, timeout_seconds=timeout_seconds)

    return QuickSearchService(
        client_factory=client_factory, research_policy=settings.policy, max_extracts=min(2, settings.max_extracts),
    )
