"""Fresh web retrieval for assistant knowledge context."""
from __future__ import annotations

import os
import re
from typing import Any

import httpx

from .models import AssistantContextItem

_DEFAULT_TIMEOUT_SECONDS = 8.0
_AUTO_SEARCH_PATTERNS = (
    r"\b(search|look up|find online|browse|on the web|internet)\b",
    r"\b(latest|current|today|tonight|yesterday|tomorrow|recent|newest|news)\b",
    r"\b(price|release date|schedule|score|weather|forecast|exchange rate|stock)\b",
    r"\b(who is the current|what is the current|is .* still)\b",
)


def should_search_automatically(query: str) -> bool:
    normalized = " ".join(query.lower().split())
    return any(re.search(pattern, normalized) for pattern in _AUTO_SEARCH_PATTERNS)


class WebSearchClient:
    """Provider-neutral web retrieval with a keyless DuckDuckGo fallback."""

    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.provider = (provider or os.environ.get("OMNIX_WEB_SEARCH_PROVIDER") or "duckduckgo").strip().lower()
        self.api_key = api_key if api_key is not None else os.environ.get("OMNIX_WEB_SEARCH_API_KEY", "")
        self.timeout_seconds = timeout_seconds or float(os.environ.get("OMNIX_WEB_SEARCH_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS))
        self.client = client

    def search(self, query: str, max_results: int = 5) -> list[AssistantContextItem]:
        clean_query = " ".join(query.split()).strip()
        if not clean_query:
            return []
        client = self.client or httpx.Client(timeout=self.timeout_seconds, follow_redirects=True)
        close_client = self.client is None
        try:
            if self.provider == "brave":
                return self._search_brave(client, clean_query, max_results)
            if self.provider == "tavily":
                return self._search_tavily(client, clean_query, max_results)
            return self._search_duckduckgo(client, clean_query, max_results)
        finally:
            if close_client:
                client.close()

    def _search_duckduckgo(self, client: httpx.Client, query: str, max_results: int) -> list[AssistantContextItem]:
        response = client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1", "no_redirect": "1"},
        )
        response.raise_for_status()
        payload = response.json()
        rows: list[dict[str, str]] = []
        abstract = str(payload.get("AbstractText") or "").strip()
        abstract_url = str(payload.get("AbstractURL") or "").strip()
        heading = str(payload.get("Heading") or query).strip()
        if abstract:
            rows.append({"title": heading, "url": abstract_url, "snippet": abstract})
        for row in payload.get("Results") or []:
            self._append_duckduckgo_row(rows, row)
        for row in payload.get("RelatedTopics") or []:
            if isinstance(row, dict) and isinstance(row.get("Topics"), list):
                for nested in row["Topics"]:
                    self._append_duckduckgo_row(rows, nested)
            else:
                self._append_duckduckgo_row(rows, row)
        return self._context_items(rows, max_results, provider="duckduckgo")

    def _search_brave(self, client: httpx.Client, query: str, max_results: int) -> list[AssistantContextItem]:
        if not self.api_key:
            raise RuntimeError("OMNIX_WEB_SEARCH_API_KEY is required for the Brave provider")
        response = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results, "text_decorations": "false"},
            headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
        )
        response.raise_for_status()
        results = response.json().get("web", {}).get("results", [])
        rows = [
            {
                "title": str(row.get("title") or query),
                "url": str(row.get("url") or ""),
                "snippet": str(row.get("description") or ""),
            }
            for row in results
        ]
        return self._context_items(rows, max_results, provider="brave")

    def _search_tavily(self, client: httpx.Client, query: str, max_results: int) -> list[AssistantContextItem]:
        if not self.api_key:
            raise RuntimeError("OMNIX_WEB_SEARCH_API_KEY is required for the Tavily provider")
        response = client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": False,
            },
        )
        response.raise_for_status()
        rows = [
            {
                "title": str(row.get("title") or query),
                "url": str(row.get("url") or ""),
                "snippet": str(row.get("content") or ""),
            }
            for row in response.json().get("results", [])
        ]
        return self._context_items(rows, max_results, provider="tavily")

    @staticmethod
    def _append_duckduckgo_row(rows: list[dict[str, str]], row: Any) -> None:
        if not isinstance(row, dict):
            return
        snippet = str(row.get("Text") or "").strip()
        url = str(row.get("FirstURL") or "").strip()
        if not snippet:
            return
        title = snippet.split(" - ", 1)[0].strip() or "Web result"
        rows.append({"title": title, "url": url, "snippet": snippet})

    @staticmethod
    def _context_items(rows: list[dict[str, str]], max_results: int, *, provider: str) -> list[AssistantContextItem]:
        items: list[AssistantContextItem] = []
        seen_urls: set[str] = set()
        for row in rows:
            snippet = " ".join(row.get("snippet", "").split()).strip()
            url = row.get("url", "").strip()
            if not snippet or (url and url in seen_urls):
                continue
            if url:
                seen_urls.add(url)
            items.append(
                AssistantContextItem(
                    source_id="web_search",
                    title=" ".join(row.get("title", "Web result").split())[:240] or "Web result",
                    content=snippet[:1800],
                    url=url or None,
                    metadata={"provider": provider},
                )
            )
            if len(items) >= max_results:
                break
        return items
