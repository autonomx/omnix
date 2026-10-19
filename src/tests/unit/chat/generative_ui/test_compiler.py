"""The reply compiler and its shared golden fixtures (GUI-1.3).

The fixtures in ``resources/chat/generative_ui/fixtures`` are also read by the
web app's Vitest suite, so the server and client contracts cannot drift. Set
``OMNIX_UPDATE_GUI_FIXTURES=1`` to rewrite their ``expected`` payloads after an
intended compiler change, then review the diff.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.platform.chat.generative_ui import COMPILER_VERSION, ChatUiPayload, CompileScope, compile_chat_ui
from app.platform.chat.generative_ui.bindings import binding_sources
from app.platform.chat.generative_ui.compiler import rebase_reply_ui, rebase_ui_after_rewrite

FIXTURES = Path(__file__).resolve().parents[5] / "resources" / "chat" / "generative_ui" / "fixtures"
FENCE = "```"
CLOCK = lambda: datetime(2026, 10, 11, 14, 3, 22, tzinfo=timezone.utc)  # noqa: E731


def fixture_scope(fixture: dict) -> CompileScope:
    scope = fixture.get("scope") or {}
    compiled_at = datetime.fromisoformat(fixture["compiled_at"].replace("Z", "+00:00"))
    return CompileScope(
        clock=lambda: compiled_at,
        sources=binding_sources(scope.get("context_items")),
        market_symbols=scope.get("market_symbols"),
    )


def fixture_paths() -> list[Path]:
    return sorted(FIXTURES.glob("*.json"))


def test_fixtures_exist():
    assert len(fixture_paths()) >= 10


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda path: path.stem)
def test_golden_fixture(path: Path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    payload = compile_chat_ui(fixture["content"], fixture_scope(fixture))
    if os.environ.get("OMNIX_UPDATE_GUI_FIXTURES") == "1":
        fixture["expected"] = payload
        path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert payload == fixture["expected"]
    assert payload is not None
    ChatUiPayload.model_validate(payload)
    assert "omnix-ui" not in payload["text"] and "omnix-ui" not in payload["speech"]


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda path: path.stem)
def test_markdown_offsets_reproduce_the_prose_and_never_include_a_fence(path: Path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    payload = fixture["expected"]
    content = fixture["content"]
    for segment in payload["segments"]:
        if segment["kind"] != "markdown":
            continue
        span = content[segment["start"]:segment["end"]]
        assert span.strip()
        assert "omnix-ui" not in span
        assert span.strip() in payload["text"]


def test_identical_input_and_clock_give_byte_identical_output():
    path = FIXTURES / "mixed_reply.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    first = json.dumps(compile_chat_ui(fixture["content"], fixture_scope(fixture)), sort_keys=True)
    second = json.dumps(compile_chat_ui(fixture["content"], fixture_scope(fixture)), sort_keys=True)

    assert first == second
    assert json.loads(first)["compiler_version"] == COMPILER_VERSION


def test_a_reply_without_an_omnix_ui_fence_compiles_to_none():
    assert compile_chat_ui("Plain answer with ```python\nprint(1)\n``` code.", CompileScope(clock=CLOCK)) is None
    assert compile_chat_ui("Mentions omnix-ui in prose only.", CompileScope(clock=CLOCK)) is None


def test_an_interrupted_reply_compiles_to_none():
    content = f'{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "A", "value": "1"}}]}}\n{FENCE}'

    assert compile_chat_ui(content, CompileScope(clock=CLOCK, interrupted=True)) is None


def test_an_all_invalid_reply_still_has_readable_text_and_speech():
    content = f"{FENCE}omnix-ui\n{{oops\n{FENCE}\n{FENCE}omnix-ui\n[1, 2]\n{FENCE}\n{FENCE}omnix-ui\n{{\"type\": \"mystery\"}}\n{FENCE}"
    payload = compile_chat_ui(content, CompileScope(clock=CLOCK))

    assert payload["blocks"] == {}
    assert [segment["kind"] for segment in payload["segments"]] == ["text", "text", "text"]
    assert payload["text"] == (
        "[A block could not be shown.]\n\n[A content block could not be shown.]\n\n[A mystery block could not be shown.]"
    )
    assert payload["speech"] == payload["text"]
    assert [item["code"] for item in payload["diagnostics"]] == ["invalid_json", "not_object", "unknown_type"]


def test_ids_are_kept_when_valid_and_assigned_when_missing_duplicated_or_malformed():
    stats = '"type": "stats", "items": [{"label": "A", "value": "1"}]'
    content = "\n".join(
        f"{FENCE}omnix-ui\n{{{spec}}}\n{FENCE}"
        for spec in (f'"id": "b2", {stats}', stats, f'"id": "b2", {stats}', f'"id": "9 bad", {stats}')
    )
    payload = compile_chat_ui(content, CompileScope(clock=CLOCK))

    assert list(payload["blocks"]) == ["b2", "b1", "b3", "b4"]
    assert [(item["code"], item["block"]) for item in payload["diagnostics"]] == [("duplicate_id", "b3"), ("invalid_id", "b4")]


def test_blocks_beyond_eight_become_text():
    block = f'{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "A", "value": "1"}}]}}\n{FENCE}'
    payload = compile_chat_ui("\n".join([block] * 10), CompileScope(clock=CLOCK))

    assert len(payload["blocks"]) == 8
    assert payload["segments"][-1] == {"kind": "text", "text": "A: 1."}
    assert [item["code"] for item in payload["diagnostics"]] == ["too_many_blocks", "too_many_blocks"]


def test_the_payload_cap_turns_the_largest_blocks_into_text_first():
    def chart(points: int) -> str:
        data = [[f"c{i:04d}", i] for i in range(points)]
        return f'{FENCE}omnix-ui\n{json.dumps({"type": "chart", "kind": "bar", "x": {"type": "category"}, "series": [{"name": "S", "points": data}]})}\n{FENCE}'

    content = "\n".join([chart(1_900)] * 6 + [chart(10)])
    payload = compile_chat_ui(content, CompileScope(clock=CLOCK))

    assert len(json.dumps(payload, separators=(",", ":"))) <= 128 * 1024
    degraded = [item["block"] for item in payload["diagnostics"] if item["code"] == "payload_too_large"]
    assert degraded and "b7" not in degraded
    assert "b7" in payload["blocks"]


def test_rebase_appends_a_markdown_span_for_an_appended_tail():
    content = f'Answer.\n\n{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "A", "value": "1"}}]}}\n{FENCE}'
    ui = compile_chat_ui(content, CompileScope(clock=CLOCK))
    appended = content + "\n\n> Research mode notice: limited."

    rebased = rebase_ui_after_rewrite(ui, content, appended)
    assert rebased["segments"][-1] == {"kind": "markdown", "start": len(content), "end": len(appended)}
    assert rebased["text"].endswith("> Research mode notice: limited.")
    assert rebased["speech"].endswith("Research mode notice: limited.")
    assert rebase_ui_after_rewrite(ui, content, "Rewritten.") is None

    metadata = {"ui": ui}
    rebase_reply_ui(metadata, content, "Rewritten.")
    assert metadata == {"ui_error": {"code": "content_rewritten"}}


def test_research_citation_validation_rebases_the_stored_ui(tmp_path):
    from app.platform.chat import ChatMessage, CreateChatSessionRequest
    from app.platform.chat.research_citations import validate_completed_research_reply
    from app.platform.chat.store import ChatSessionStore

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Research"))
    content = f'Rates held [S1].\n\n{FENCE}omnix-ui\n{{"type": "sources", "refs": [{{"bind": "source:1"}}]}}\n{FENCE}'
    items = [{"source_id": "web_search", "title": "[S1] Fed", "url": "https://example.com/fed", "metadata": {"citation_label": "S1"}}]
    ui = compile_chat_ui(content, CompileScope(clock=CLOCK, sources=binding_sources(items)))
    session.messages.extend((
        ChatMessage(id="msg:user", role="user", content="Rates?", created_at="2026-10-11T00:00:00Z"),
        ChatMessage(id="msg:reply", role="assistant", content=content, created_at="2026-10-11T00:00:01Z",
                    metadata={"reply_to_message_id": "msg:user", "ui": ui}),
    ))
    store._save_session(session)  # noqa: SLF001 - persistence fixture

    updated = validate_completed_research_reply(
        store, session.id, "msg:user", items, render=lambda text, _items: (text + "\n\nNote: limited evidence.", {}),
    )
    saved = updated.messages[-1]

    assert saved.content.startswith(content)
    assert saved.metadata["ui"]["segments"][-1] == {"kind": "markdown", "start": len(content), "end": len(saved.content)}
    assert saved.metadata["ui"]["text"].endswith("Note: limited evidence.")
