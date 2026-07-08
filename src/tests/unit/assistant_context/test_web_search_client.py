from __future__ import annotations

from datetime import date

from app.assistant_context.web_search import WebSearchClient


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
