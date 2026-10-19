"""The save paths' compile helper and its resolvers (GUI-1.4, GUI-4.1, GUI-4.2)."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from app.platform.chat.generative_ui import finalize_reply_ui
from app.platform.chat.generative_ui import finalize as finalize_module
from app.platform.chat.generative_ui.bindings import binding_sources, requested_market_symbols

FENCE = "```"
CLOCK = lambda: datetime(2026, 10, 11, 14, 3, 22, tzinfo=timezone.utc)  # noqa: E731
STATS = f'Prose.\n\n{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "A", "value": "1"}}]}}\n{FENCE}'
PRICE = f'{FENCE}omnix-ui\n{{"type": "price_chart", "symbol": "AAPL", "interval": "1d", "range": "6M"}}\n{FENCE}'


class Lookup:
    def __init__(self, known: dict[str, str], delay: float = 0.0) -> None:
        self.known = known
        self.delay = delay
        self.calls: list[str] = []

    def instrument_id(self, symbol: str) -> str | None:
        self.calls.append(symbol)
        time.sleep(self.delay)
        return self.known.get(symbol)


def test_a_fenced_reply_gets_ui_and_a_plain_reply_gets_nothing():
    assert finalize_reply_ui("Plain reply.", {"generation_status": "completed"}) == {}
    result = finalize_reply_ui(STATS, {"generation_status": "completed"}, clock=CLOCK)
    assert set(result) == {"ui"}
    assert result["ui"]["text"] == "Prose.\n\nA: 1."


def test_memory_commands_and_interrupted_replies_are_excluded():
    assert finalize_reply_ui(STATS, {"memory_command": {"kind": "list"}}) == {}
    assert finalize_reply_ui(STATS, {"delivery_status": "interrupted"}) == {}
    assert finalize_reply_ui(STATS, {"generation_status": "interrupted"}) == {}


def test_a_compiler_failure_becomes_ui_error_and_never_raises(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(finalize_module, "compile_chat_ui", explode)
    result = finalize_reply_ui(STATS, {}, clock=CLOCK)

    assert result["ui_error"] == {"code": "compile_failed", "error_type": "RuntimeError"}
    # A block-free payload keeps the fence out of history, copy and speech.
    assert result["ui"]["blocks"] == {}
    assert result["ui"]["text"] == "Prose.\n\n[A block could not be shown.]"
    assert "{" not in result["ui"]["speech"]
    assert result["ui"]["diagnostics"] == [{"code": "compile_failed", "severity": "degraded"}]


def test_when_even_the_fallback_fails_only_the_error_is_recorded(monkeypatch):
    monkeypatch.setattr(finalize_module, "compile_chat_ui", lambda *_args: 1 / 0)
    monkeypatch.setattr(finalize_module, "fallback_payload", lambda *_args: 1 / 0)

    assert finalize_reply_ui(STATS, {}) == {"ui_error": {"code": "compile_failed", "error_type": "ZeroDivisionError"}}


def test_price_chart_symbols_are_validated_before_compiling():
    lookup = Lookup({"AAPL": "equity:NASDAQ:AAPL"})
    result = finalize_reply_ui(PRICE, {}, symbol_lookup=lookup, clock=CLOCK)

    assert lookup.calls == ["AAPL"]
    block = result["ui"]["blocks"]["b1"]
    assert block["instrument_id"] == "equity:NASDAQ:AAPL"
    assert block["as_of"] == result["ui"]["compiled_at"] == "2026-10-11T14:03:22Z"


def test_an_unknown_symbol_degrades_to_text():
    result = finalize_reply_ui(PRICE, {}, symbol_lookup=Lookup({}), clock=CLOCK)

    assert result["ui"]["blocks"] == {}
    assert result["ui"]["diagnostics"][0]["code"] == "unknown_symbol"
    assert result["ui"]["text"] == "[A price chart block could not be shown.]"


def test_a_slow_symbol_lookup_degrades_to_text_without_holding_the_reply():
    started = time.perf_counter()
    result = finalize_reply_ui(PRICE, {}, symbol_lookup=Lookup({"AAPL": "x:AAPL"}, delay=2.0), symbol_timeout_seconds=0.2, clock=CLOCK)

    assert time.perf_counter() - started < 1.0
    assert result["ui"]["blocks"] == {}
    assert result["ui"]["diagnostics"][0]["code"] == "unverified_symbol"


def test_no_market_port_means_price_charts_are_unverified(monkeypatch):
    import app.runtime.ports as ports

    monkeypatch.setattr(ports, "optional", lambda _port: None)
    result = finalize_reply_ui(PRICE, {}, clock=CLOCK)

    assert result["ui"]["diagnostics"][0]["code"] == "unverified_symbol"


def test_finalize_runs_on_the_calling_thread_for_the_compile():
    seen: list[str] = []
    original = finalize_module.compile_chat_ui

    def spy(content, scope):
        seen.append(threading.current_thread().name)
        return original(content, scope)

    finalize_module.compile_chat_ui = spy
    try:
        finalize_reply_ui(STATS, {})
    finally:
        finalize_module.compile_chat_ui = original
    assert seen == [threading.current_thread().name]


def test_binding_sources_number_context_items_and_research_citations():
    sources = binding_sources([
        {"source_id": "notes", "title": "Meeting notes", "content": "..."},
        {"source_id": "web_search", "title": "[S1] Fed holds", "url": "https://example.com/fed", "metadata": {"citation_label": "S1"}},
        "not an item",
    ])

    assert sorted(sources) == ["context:1", "context:2", "source:1"]
    assert sources["source:1"].title == "Fed holds"
    assert sources["source:1"].citation == "S1"
    assert sources["context:1"].url is None


def test_requested_symbols_come_only_from_valid_price_chart_blocks():
    content = PRICE + "\n" + PRICE.replace("AAPL", "msft") + "\n" + STATS + "\n" + PRICE.replace("AAPL", "bad symbol!")

    assert requested_market_symbols(content) == ["AAPL", "MSFT"]


def test_ui_metrics_count_rendered_and_dropped_blocks_and_diagnostic_codes():
    from app.platform.chat.generative_ui import attach_reply_ui

    content = STATS + "\n" + f'{FENCE}omnix-ui\n{{"type": "mystery"}}\n{FENCE}' + "\n" + f'{FENCE}omnix-ui\n{{"type": "stats", "x": 1, "items": [{{"label": "B", "value": "2"}}]}}\n{FENCE}'
    metadata = {"provider_metrics": {"provider": "lmstudio", "tokens_per_second": 12.0}}
    attach_reply_ui(content, metadata)

    assert metadata["provider_metrics"] == {
        "provider": "lmstudio", "tokens_per_second": 12.0,
        "ui_blocks": 2, "ui_dropped": 1, "ui_diagnostics": {"unknown_type": 1, "unknown_prop": 1},
    }


def test_ui_metrics_record_a_failed_compile_and_ignore_plain_replies(monkeypatch):
    from app.platform.chat.generative_ui import attach_reply_ui

    plain: dict = {}
    attach_reply_ui("Plain.", plain)
    assert plain == {}

    monkeypatch.setattr(finalize_module, "compile_chat_ui", lambda *_args: 1 / 0)
    failed: dict = {}
    attach_reply_ui(STATS, failed)
    assert failed["provider_metrics"] == {"ui_error": "compile_failed"}
