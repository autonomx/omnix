"""The V1 block catalog: normalization, limits and projections (GUI-1.1)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.platform.chat.generative_ui import CATALOG, CompileScope, compile_chat_ui
from app.platform.chat.generative_ui.catalog import BoundSource, lttb

FENCE = "```"
SCOPE = CompileScope(
    clock=lambda: datetime(2026, 10, 11, 14, 3, 22, tzinfo=timezone.utc),
    sources={
        "source:1": BoundSource(ref="source:1", title="Fed holds rates", url="https://example.com/fed", citation="S1"),
        "source:2": BoundSource(ref="source:2", title="Dot plot", url="https://example.com/dots", citation="S2"),
    },
    market_symbols={"AAPL": "equity:NASDAQ:AAPL"},
)


def compile_block(spec: dict, scope: CompileScope = SCOPE) -> tuple[dict | None, dict]:
    payload = compile_chat_ui(f"{FENCE}omnix-ui\n{json.dumps(spec)}\n{FENCE}", scope)
    assert payload is not None
    block = next(iter(payload["blocks"].values()), None)
    return block, payload


def codes(payload: dict) -> list[str]:
    return [item["code"] for item in payload["diagnostics"]]


@pytest.mark.parametrize("block_type", sorted(CATALOG))
def test_every_catalog_example_compiles_with_both_projections(block_type):
    block, payload = compile_block(CATALOG[block_type].example)

    assert block is not None, payload["diagnostics"]
    assert block["type"] == block_type
    assert payload["text"].strip() and "{" not in payload["text"]
    assert payload["speech"].strip() and "{" not in payload["speech"]


def test_stats_projections_keep_every_value_in_text_and_summarize_speech():
    block, payload = compile_block({"type": "stats", "items": [
        {"label": "Revenue", "value": "$6,930", "delta": "+4.1%", "trend": "up"},
        {"label": "Orders", "value": 212},
        {"label": "Margin", "value": "41%", "delta": "-1.0%"},
    ]})

    assert payload["text"] == "Revenue: $6,930 (+4.1%). Orders: 212. Margin: 41% (-1.0%)."
    assert payload["speech"] == "Three headline figures: including Revenue $6,930, up 4.1%; and Orders 212."
    assert block["provenance"] == "model"


def test_unknown_props_are_dropped_and_reported():
    block, payload = compile_block({"type": "stats", "style": "x", "items": [{"label": "A", "value": "1", "color": "red"}]})

    assert block["items"] == [{"label": "A", "value": "1"}]
    assert [(item["code"], item["path"]) for item in payload["diagnostics"]] == [
        ("unknown_prop", "style"), ("unknown_prop", "items[0].color"),
    ]


def test_bad_literals_drop_the_prop_not_the_block():
    block, payload = compile_block({"type": "stats", "items": [{"label": "A", "value": "1", "trend": "sideways", "tone": "#f00"}]})

    assert block["items"] == [{"label": "A", "value": "1"}]
    assert codes(payload) == ["invalid_prop", "invalid_prop"]


def test_a_bad_required_literal_degrades_the_block_to_text():
    block, payload = compile_block({"type": "chart", "kind": "pie", "series": [{"name": "A", "points": [["x", 1]]}]})

    assert block is None
    assert payload["segments"] == [{"kind": "text", "text": "A"}]
    assert codes(payload)[-1] == "invalid_prop"


def test_stats_are_capped_at_six_items_and_need_one_valid_item():
    block, payload = compile_block({"type": "stats", "items": [{"label": f"L{i}", "value": str(i)} for i in range(9)]})
    assert len(block["items"]) == 6
    assert "too_many_items" in codes(payload)

    block, payload = compile_block({"type": "stats", "items": [{"label": "only label"}]})
    assert block is None
    assert codes(payload) == ["invalid_item", "no_valid_items"]


def test_strings_are_truncated_to_their_limits():
    block, payload = compile_block({"type": "stats", "items": [{"label": "L" * 300, "value": "1", "hint": "h" * 2500}]})

    assert len(block["items"][0]["label"]) == 120
    assert len(block["items"][0]["hint"]) == 2000
    assert codes(payload) == ["truncated", "truncated"]


def test_charts_keep_six_series_and_downsample_long_time_series():
    points = [[1_700_000_000 + i * 60, float(i % 97)] for i in range(5_000)]
    series = [{"name": f"S{i}", "points": points} for i in range(8)]
    block, payload = compile_block({"type": "chart", "kind": "line", "x": {"type": "time"}, "series": series})

    assert len(block["series"]) == 6
    # 2,000 points per series first (LTTB), then fewer until the block fits 32 KB.
    lengths = {len(item["points"]) for item in block["series"]}
    assert len(lengths) == 1 and 50 <= lengths.pop() < 2_000
    assert len(json.dumps(block, separators=(",", ":"))) <= 32 * 1024
    assert block["series"][0]["points"][0] == [1_700_000_000, 0.0]
    assert block["series"][0]["points"][-1] == [1_700_000_000 + 4_999 * 60, float(4_999 % 97)]
    assert codes(payload) == ["too_many_items"] + ["downsampled"] * 7


def test_a_category_chart_too_large_for_a_block_becomes_text():
    points = [[f"category {i}", float(i)] for i in range(2_000)]
    block, payload = compile_block({"type": "chart", "kind": "bar", "x": {"type": "category"}, "series": [{"name": "A", "points": points}]})

    assert block is None
    assert codes(payload) == ["block_too_large"]
    assert payload["text"].startswith("Bar chart\nA: min 0, max 1,999")


def test_time_points_are_sorted_deduplicated_and_invalid_points_dropped():
    block, payload = compile_block({"type": "chart", "kind": "area", "series": [{"name": "A", "points": [
        ["2026-10-02", 2], ["2026-10-01", 1], ["2026-10-02", 3], ["not a date", 4], ["2026-10-03", None],
    ]}]})

    assert block["x"]["type"] == "time"
    assert block["series"][0]["points"] == [[1790812800, 1.0], [1790899200, 3.0]]
    assert codes(payload) == ["invalid_point"]


def test_lttb_keeps_the_end_points_and_the_extremes():
    points = [(i, 0.0) for i in range(100)]
    points[50] = (50, 100.0)
    sampled = lttb(points, 10)

    assert len(sampled) == 10
    assert sampled[0] == points[0] and sampled[-1] == points[-1]
    assert (50, 100.0) in sampled


def test_price_charts_need_a_validated_symbol():
    block, payload = compile_block({"type": "price_chart", "symbol": "aapl", "interval": "1D", "range": "6m"})
    assert block == {
        "type": "price_chart", "id": "b1", "v": 1, "symbol": "AAPL", "instrument_id": "equity:NASDAQ:AAPL",
        "interval": "1d", "range": "6M", "as_of": "2026-10-11T14:03:22Z", "provenance": "market_data", "bindings": [],
    }
    assert payload["text"] == "AAPL daily, 6M to 2026-10-11"

    block, payload = compile_block({"type": "price_chart", "symbol": "ZZZZ", "interval": "1d", "range": "6M"})
    assert block is None and codes(payload) == ["unknown_symbol"]

    unchecked = CompileScope(clock=SCOPE.clock)
    block, payload = compile_block({"type": "price_chart", "symbol": "AAPL"}, unchecked)
    assert block is None and codes(payload) == ["unverified_symbol"]


def test_sources_resolve_bindings_and_drop_unknown_or_literal_refs():
    block, payload = compile_block({"type": "sources", "refs": [
        {"bind": "source:2"}, "source:1", {"bind": "source:7"}, {"title": "Made up", "url": "https://x"}, {"bind": "source:1.title"},
    ]})

    assert [ref["ref"] for ref in block["refs"]] == ["source:2", "source:1"]
    assert block["refs"][0] == {"ref": "source:2", "title": "Dot plot", "citation": "S2", "url": "https://example.com/dots"}
    assert codes(payload) == ["unresolved_binding", "invalid_ref", "binding_type_mismatch"]
    assert payload["speech"] == "Two sources."


def test_a_bound_value_is_frozen_with_its_source():
    block, _ = compile_block({"type": "stats", "items": [{"label": "Story", "value": {"bind": "source:1.title"}}]})

    assert block["items"][0]["value"] == "Fed holds rates"
    assert block["provenance"] == "bound"
    assert block["bindings"] == [{"path": "items[0].value", "ref": "source:1", "title": "Fed holds rates", "url": "https://example.com/fed"}]


def test_choices_refuse_a_separate_message_and_drop_long_or_duplicate_labels():
    block, payload = compile_block({"type": "choices", "options": [{"label": "Go"}, {"label": "Stop", "message": "rm -rf"}]})
    assert block is None and codes(payload) == ["separate_message_field"]

    block, payload = compile_block({"type": "choices", "options": ["Go", "Go", "x" * 161, "Stop", "A", "B", "C", "D", "E"]})
    assert [option["label"] for option in block["options"]] == ["Go", "Stop", "A", "B", "C", "D"]
    assert codes(payload) == ["option_dropped", "option_dropped", "too_many_items"]
    assert payload["text"] == "Options: Go; Stop; A; B; C; D"


def test_forms_validate_fields_and_template_placeholders():
    spec = {"type": "form", "template": "Run {symbol} at {risk}", "fields": [
        {"name": "symbol", "kind": "select", "options": ["AAPL", "MSFT"], "default": "TSLA"},
        {"name": "risk", "kind": "slider", "min": 1, "max": 5, "default": 9},
        {"name": "bad name", "kind": "text"},
        {"name": "flag", "kind": "toggle", "default": True},
    ]}
    block, payload = compile_block(spec)
    assert [item["name"] for item in block["fields"]] == ["symbol", "risk", "flag"]
    assert "default" not in block["fields"][0] and "default" not in block["fields"][1]
    assert block["fields"][2]["default"] is True
    assert codes(payload) == ["invalid_field"]
    assert payload["speech"] == "A form with three fields."

    block, payload = compile_block({**spec, "template": "Run {unknown}"})
    assert block is None and codes(payload)[-1] == "invalid_template"

    block, payload = compile_block({**spec, "template": "x" * 501})
    assert block is None and codes(payload) == ["template_too_long"]
