"""Podcast research: one web search on the episode's topic, returned as source notes the producer edits before the
script is written (owner request 2026-11-24)."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.apps.story import feature, podcast_research
from app.apps.story.podcast_research import (
    NOTES_LIMIT,
    QUERY_CHARS,
    SOURCE_CHARS,
    PodcastResearchRequest,
    research_podcast_topic,
    research_query,
    source_notes,
)
from app.security.permissions import declared_permission


class Search:
    """Research's quick search, faked: records each query and returns ``items`` with ``status``."""

    def __init__(self, items: list[dict], status: str = "completed") -> None:
        self.items = items
        self.status = status
        self.calls: list[tuple[str, int, str]] = []

    def search(self, query: str, max_results: int, *, identity: str):
        self.calls.append((query, max_results, identity))
        return SimpleNamespace(items=self.items, diagnostics={"status": self.status, "provider": "brave"})


def _item(title: str, content: str, url: str | None = "https://example.org/a") -> dict:
    return {"source_id": "web_search", "title": title, "content": content, "url": url}


def test_the_query_is_the_title_and_the_start_of_the_brief_cut_at_a_word():
    assert research_query("  Local AI ", "What changes\nwhen assistants run at home?") == (
        "Local AI What changes when assistants run at home?"
    )
    long = research_query("Title", "word " * 100)
    assert len(long) <= QUERY_CHARS and long.endswith("word")
    assert research_query("", "  ") == ""


def test_each_result_with_text_becomes_a_note_with_its_title_and_link_until_the_notes_are_full():
    notes, sources = source_notes([
        _item("GPU prices", "A 4090   sells for\n$1,600."),
        _item("No text", ""),
        _item("No link", "Local models use 8 GB.", url=None),
        _item("Long", "fact " * 1000),
    ])
    assert notes.startswith("Web research, 3 sources (check before use):\n\n")
    assert "- GPU prices (https://example.org/a)\n  A 4090 sells for $1,600." in notes
    assert "- No link\n  Local models use 8 GB." in notes
    assert "No text" not in notes
    assert [source.title for source in sources] == ["GPU prices", "No link", "Long"]
    long_note = notes.split("- Long (https://example.org/a)\n  ", 1)[1]
    assert len(long_note) <= SOURCE_CHARS + 4 and long_note.endswith(" ...")

    many, kept = source_notes([_item(f"Source {index}", "fact " * 300) for index in range(20)])
    assert len(many) <= NOTES_LIMIT + 100 and 0 < len(kept) < 20
    assert source_notes([_item("Empty", "")]) == ("", [])


def test_research_searches_once_and_returns_the_notes():
    search = Search([_item("GPU prices", "A 4090 sells for $1,600.")])
    reply = research_podcast_topic(PodcastResearchRequest(title="AI at home", brief="Local models"), search_factory=lambda: search)
    assert search.calls == [("AI at home Local models", 5, "podcast")]
    assert reply.status == "ok" and reply.provider == "brave" and reply.query == "AI at home Local models"
    assert "A 4090 sells for $1,600." in reply.notes
    assert [source.model_dump() for source in reply.sources] == [{"title": "GPU prices", "url": "https://example.org/a"}]
    assert reply.message == "Added notes from 1 web source. Check them before you generate."


def test_research_says_why_there_are_no_notes():
    nothing = Search([])
    assert research_podcast_topic(PodcastResearchRequest(), search_factory=lambda: nothing).status == "empty"
    assert nothing.calls == []  # no topic, no search
    empty = research_podcast_topic(PodcastResearchRequest(title="T"), search_factory=lambda: nothing)
    assert (empty.status, empty.message) == ("empty", "The web search found nothing on this topic.")
    failed = research_podcast_topic(PodcastResearchRequest(title="T"), search_factory=lambda: Search([], "failed"))
    assert failed.status == "failed" and "did not answer" in failed.message

    class Raising:
        def search(self, query: str, max_results: int, *, identity: str):
            raise TimeoutError("provider timed out")

    raised = research_podcast_topic(PodcastResearchRequest(title="T"), search_factory=Raising)
    assert (raised.status, raised.query) == ("failed", "T") and "did not answer" in raised.message


def test_without_the_research_feature_nothing_is_searched(monkeypatch):
    monkeypatch.setattr(podcast_research, "_research_enabled", lambda: False)
    monkeypatch.setattr(podcast_research, "_quick_search", lambda _settings: (_ for _ in ()).throw(AssertionError))
    reply = research_podcast_topic(PodcastResearchRequest(title="T"))
    assert (reply.status, reply.message) == ("unavailable", "Web research is not part of this install.")


def test_with_quick_search_switched_off_nothing_is_searched(monkeypatch):
    from app.platform.research.contracts import ResearchReleasePolicy, ResearchRuntimeSettings, research_policy_from_env

    monkeypatch.setattr(podcast_research, "_research_enabled", lambda: True)
    monkeypatch.setattr(
        "app.platform.research.contracts.load_research_runtime_settings",
        lambda: ResearchRuntimeSettings(policy=research_policy_from_env()),
    )
    monkeypatch.setattr(
        "app.platform.research.contracts.research_release_policy_from_env",
        lambda: ResearchReleasePolicy(quick_enabled=False),
    )
    monkeypatch.setattr(podcast_research, "_quick_search", lambda _settings: (_ for _ in ()).throw(AssertionError))
    reply = research_podcast_topic(PodcastResearchRequest(title="T"))
    assert reply.status == "unavailable" and reply.message.startswith("Web search is switched off (")


def test_the_route_needs_research_permission_and_returns_the_notes(monkeypatch):
    monkeypatch.setattr(
        feature, "research_podcast_topic",
        lambda request: research_podcast_topic(request, search_factory=lambda: Search([_item("A", "Fact.")])),
    )
    app = FastAPI()
    router = feature._podcast_research_router(None)
    app.include_router(router)
    [route] = [route for route in router.routes if getattr(route, "path", "") == "/api/podcast/research"]
    assert declared_permission(route, "POST") == "research:run"
    response = TestClient(app).post("/api/podcast/research", json={"title": "AI at home", "brief": "Local models"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok" and "Fact." in response.json()["notes"]
