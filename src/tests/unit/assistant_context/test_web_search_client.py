from __future__ import annotations

from datetime import date

from app.assistant_context.web_search import (
    WebSearchClient,
    _playwright_duckduckgo_rows,
    _playwright_external_link_rows,
)


class FakeResponse:
    def __init__(self, *, payload=None, text: str = "") -> None:
        self.payload = payload or {}
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.requests.append((url, kwargs))
        if "api.duckduckgo.com" in url:
            return FakeResponse(payload={"RelatedTopics": [], "Results": []})
        return FakeResponse(
            text="""
            <html>
              <body>
                <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.test%2Fresearch">Example result</a>
                <a class="result__snippet">Evidence-backed result snippet.</a>
              </body>
            </html>
            """
        )


def test_duckduckgo_html_fallback_runs_when_instant_answer_is_empty() -> None:
    fake = FakeHttpClient()
    client = WebSearchClient(provider="duckduckgo", client=fake)

    results = client.search("ordinary web query", max_results=3)

    assert [url for url, _ in fake.requests] == [
        "https://api.duckduckgo.com/",
        "https://html.duckduckgo.com/html/",
    ]
    assert len(results) == 1
    assert results[0].title == "Example result"
    assert results[0].url == "https://example.test/research"
    assert results[0].content == "Evidence-backed result snippet."


def test_relative_time_queries_are_retried_with_exact_date() -> None:
    fake = FakeHttpClient()
    client = WebSearchClient(
        provider="duckduckgo",
        client=fake,
        today=lambda: date(2026, 7, 8),
    )

    client.search("what was today result for the topic?", max_results=2)

    queries = [request[1].get("params", {}).get("q") for request in fake.requests]
    assert "what was today result for the topic?" in queries
    assert "what was today result for the topic? July 8, 2026" in queries
    assert "what was today result for the topic? latest" in queries


class FakeLocator:
    def __init__(self, entries, index: int | None = None) -> None:
        self.entries = entries
        self.index = index

    def count(self) -> int:
        return len(self.entries)

    def nth(self, index: int):
        return FakeLocator(self.entries, index)

    def inner_text(self, timeout: int = 1000) -> str:
        entry = self.entries[self.index or 0]
        return entry["title"] if self.index is not None else entry["snippet"]

    def get_attribute(self, name: str) -> str:
        return self.entries[self.index or 0]["href"]

    def locator(self, selector: str):
        if selector.startswith("xpath="):
            return FakeLocator([self.entries[self.index or 0]])
        return FakeLocator([{"snippet": self.entries[0]["snippet"], "title": "", "href": ""}])


class FakePlaywrightPage:
    def locator(self, selector: str):
        assert selector == "a.result__a"
        return FakeLocator(
            [
                {
                    "title": "Qwen Coder benchmark",
                    "href": "/l/?uddg=https%3A%2F%2Fexample.test%2Fqwen",
                    "snippet": "Qwen Coder performs well in local coding benchmarks.",
                }
            ]
        )


def test_playwright_duckduckgo_rows_extract_titles_urls_and_snippets() -> None:
    rows = _playwright_duckduckgo_rows(FakePlaywrightPage(), 4)

    assert rows == [
        {
            "title": "Qwen Coder benchmark",
            "url": "https://example.test/qwen",
            "snippet": "Qwen Coder performs well in local coding benchmarks.",
        }
    ]


class FakeExternalLinksPage:
    def evaluate(self, script: str, max_results: int):
        return [
            {"title": "Brave", "url": "https://search.brave.com/settings", "snippet": "Internal"},
            {
                "title": "Qwen3-Coder-Next",
                "url": "https://qwen.ai/blog/qwen3-coder-next",
                "snippet": "Qwen3-Coder-Next benchmark details.",
            },
            {
                "title": "Evaluation results",
                "url": "https://eval.16x.engineer/blog/qwen3-coder-evaluation-results",
                "snippet": "Comparative coding evaluation results.",
            },
        ][:max_results]


def test_playwright_external_link_rows_skip_internal_search_links() -> None:
    rows = _playwright_external_link_rows(
        FakeExternalLinksPage(),
        2,
        internal_hosts={"search.brave.com"},
    )

    assert rows == [
        {
            "title": "Qwen3-Coder-Next",
            "url": "https://qwen.ai/blog/qwen3-coder-next",
            "snippet": "Qwen3-Coder-Next benchmark details.",
        }
    ]
