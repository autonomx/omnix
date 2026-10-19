"""Fence scanning and tolerant JSON for chat generative UI (GUI-1.2)."""
from __future__ import annotations

import time

import pytest

from app.platform.chat.generative_ui.parser import FenceJsonError, parse_fence_json, scan_fences

FENCE = "```"


def test_fences_are_found_with_offsets_that_cover_their_lines():
    content = f"Intro\n\n{FENCE}omnix-ui\n{{\"type\": \"stats\"}}\n{FENCE}\nAfter"
    [fence] = scan_fences(content)

    assert content[fence.start:fence.end] == f"{FENCE}omnix-ui\n{{\"type\": \"stats\"}}\n{FENCE}\n"
    assert fence.body == '{"type": "stats"}\n'
    assert fence.closed


def test_a_fence_indented_under_a_list_item_is_found():
    content = f"- point\n  {FENCE}omnix-ui\n  {{\"type\": \"stats\"}}\n  {FENCE}\n- next"
    [fence] = scan_fences(content)

    assert fence.body.strip() == '{"type": "stats"}'
    assert content[fence.end:] == "- next"


def test_crlf_and_lone_cr_line_endings_keep_offsets_into_the_original_text():
    content = f"Intro\r\n{FENCE}omnix-ui\r\n{{}}\r\n{FENCE}\r\nTail\rmore"
    [fence] = scan_fences(content)

    assert content[:fence.start] == "Intro\r\n"
    assert content[fence.end:] == "Tail\rmore"
    assert fence.body == "{}\r\n"


def test_backticks_inside_the_body_do_not_close_the_fence():
    content = f'{FENCE}omnix-ui\n{{"type": "stats", "title": "a ``` b"}}\n{FENCE}'
    [fence] = scan_fences(content)

    assert '"a ``` b"' in fence.body


def test_inline_and_foreign_fences_never_open_a_block():
    content = (
        "Use `omnix-ui` or ```omnix-ui {} ``` inline.\n\n"
        f"{FENCE}python\n{FENCE}omnix-ui\nprint(1)\n{FENCE}\n"
        f"{FENCE}json\n{{\"type\": \"stats\"}}\n{FENCE}"
    )
    assert scan_fences(content) == []


def test_four_space_indentation_is_not_a_fence():
    assert scan_fences(f"    {FENCE}omnix-ui\n    {{}}\n    {FENCE}") == []


def test_an_unclosed_fence_runs_to_the_end_and_says_so():
    content = f"Intro\n{FENCE}omnix-ui\n{{\"type\": \"stats\""
    [fence] = scan_fences(content)

    assert not fence.closed
    assert fence.end == len(content)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('{"a": [1, 2,], "b": {"c": 1,},}', {"a": [1, 2], "b": {"c": 1}}),
        ("{“type”: “stats”}", {"type": "stats"}),
        ("{'type': 'stats', 'title': 'it\\'s \"ok\"'}", {"type": "stats", "title": 'it\'s "ok"'}),
        ("{‘type’: ‘chart’}", {"type": "chart"}),
    ],
)
def test_repairs_are_applied_and_reported(body, expected):
    parsed = parse_fence_json(body)

    assert parsed.value == expected
    assert parsed.repaired


def test_valid_json_is_not_reported_as_repaired_and_commas_inside_strings_survive():
    parsed = parse_fence_json('{"title": "a, }", "items": []}')

    assert parsed.value == {"title": "a, }", "items": []}
    assert not parsed.repaired


def test_unrepairable_json_raises():
    with pytest.raises(FenceJsonError):
        parse_fence_json("{not json")


def test_a_100_kb_reply_is_scanned_and_repaired_in_linear_time():
    items = ",".join(f"{{'label': 'L{i}', 'value': '{i}',}}" for i in range(2_500))
    body = "{'type': 'stats', 'items': [" + items + ",],}"
    content = ("Prose line.\n" * 2_000) + f"{FENCE}omnix-ui\n{body}\n{FENCE}\n"
    assert len(content) > 100_000

    started = time.perf_counter()
    [fence] = scan_fences(content)
    parsed = parse_fence_json(fence.body)
    elapsed = time.perf_counter() - started

    assert len(parsed.value["items"]) == 2_500
    assert elapsed < 1.0
