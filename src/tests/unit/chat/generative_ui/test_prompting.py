"""Rich-replies policy, catalog instruction and prompt assembly (GUI-3.1, GUI-3.2)."""
from __future__ import annotations

import itertools
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform.chat import ChatMessage, ChatSession, CreateChatSessionRequest
from app.platform.chat.generative_ui import CompileScope, compile_chat_ui
from app.platform.chat.generative_ui.prompting import (
    RichReplyDecision,
    catalog_instruction,
    catalog_instruction_tokens,
    ui_enabled_for_turn,
)
from app.platform.chat.persistence.chat_store import PostgresChatRepositoryAdapter
from app.platform.chat.prompt_assembly import build_prompt_assembly
from app.platform.chat.prompt_rendering import render_prompt_assembly
from app.platform.chat.rich_replies_routes import create_rich_replies_router
from app.platform.chat.store import ChatSessionStore
from app.providers import model_catalog

NOW = "2026-10-11T00:00:00+00:00"
FENCE = "```"
SNAPSHOTS = Path(__file__).with_name("snapshots")
REPLY = f'Revenue held.\n\n{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "Revenue", "value": "$6,930"}}]}}\n{FENCE}'
UI = compile_chat_ui(REPLY, CompileScope(clock=lambda: datetime(2026, 10, 11, tzinfo=timezone.utc)))


def session(rich_replies: str | None = "on", interaction_mode: str = "system") -> ChatSession:
    return ChatSession(
        id="chat:gui", title="GUI", created_at=NOW, updated_at=NOW, provider_id="llm:openai", model_id="llm:openai:gpt-test",
        rich_replies=rich_replies, interaction_mode=interaction_mode, character_id="character:x" if interaction_mode == "character" else None,
        message_count=2,
        messages=[
            ChatMessage(id="msg:q", role="user", content="How was the quarter?", created_at=NOW),
            ChatMessage(id="msg:a", role="assistant", content=REPLY, created_at=NOW, metadata={"ui": UI}),
        ],
    )


def user(content: str = "And orders?", **metadata) -> ChatMessage:
    return ChatMessage(id="msg:current", role="user", content=content, created_at=NOW, metadata=metadata)


MODES = {
    "ordinary": ({}, "system", "Next?"),
    "live_voice": ({"speech_segment_id": "voice-segment:1"}, "system", "Next?"),
    "character_mode": ({}, "character", "Next?"),
    "agent_mode": ({"agent_mode": True}, "system", "Next?"),
    "deep_research": ({"research_mode": "deep"}, "system", "Next?"),
    # Memory commands are marked on the user message when they are accepted.
    "memory_command": ({"memory_command": {"action": "remember"}}, "system", "/remember I like tea"),
}


@pytest.mark.parametrize(
    ("setting", "level", "mode"),
    list(itertools.product(("on", "off", None), ("none", "basic", "full"), sorted(MODES))),
)
def test_policy_matrix(setting, level, mode):
    metadata, interaction, content = MODES[mode]
    decision = ui_enabled_for_turn(
        session(setting, interaction), user(content, **metadata), capability=lambda _provider, _model: level,
    )

    expected = setting == "on" and level != "none" and mode == "ordinary"
    assert decision.enabled is expected
    if setting != "on":
        assert decision.reason == "session_setting_off"
    elif level == "none":
        assert decision.reason == "model_not_enabled"
    elif mode != "ordinary":
        assert decision.reason == mode


def test_the_routed_model_decides_and_every_model_starts_disabled():
    routed = user(omnix_provider_route={"provider_id": "claude_cli", "model_id": "haiku"})
    seen: list[tuple] = []

    ui_enabled_for_turn(session(), routed, capability=lambda provider, model: seen.append((provider, model)) or "none")

    assert seen == [("claude_cli", "haiku")]
    assert model_catalog.rich_ui_capability("llm:openai", "llm:openai:gpt-test") == "none"
    assert ui_enabled_for_turn(session(), user()).reason == "model_not_enabled"


@pytest.mark.parametrize("level", ["basic", "full"])
def test_catalog_instruction_snapshot(level):
    text = catalog_instruction(level)
    path = SNAPSHOTS / f"catalog_instruction_{level}.txt"
    if os.environ.get("OMNIX_UPDATE_GUI_FIXTURES") == "1":
        path.parent.mkdir(exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")
    assert text + "\n" == path.read_text(encoding="utf-8")
    assert catalog_instruction_tokens(level) <= 450
    assert catalog_instruction("none") == ""


def test_basic_level_teaches_only_stats_and_charts():
    basic = catalog_instruction("basic")

    assert "- stats:" in basic and "- chart:" in basic
    for name in ("price_chart", "sources", "choices", "form"):
        assert f"- {name}:" not in basic


def _rendered(decision: RichReplyDecision | None, chat_session: ChatSession | None = None, identity_resolver=None):
    assembly = build_prompt_assembly(
        chat_session or session(), user(), global_system_prompt="System", rich_replies=decision, identity_resolver=identity_resolver,
    )
    return assembly, render_prompt_assembly(assembly)


def test_enabled_turns_see_raw_blocks_and_the_instruction_in_the_budget():
    enabled = RichReplyDecision(True, "full", "enabled")
    assembly, rendered = _rendered(enabled)
    _, plain = _rendered(None)

    prompt = [message.content for message in rendered.messages]
    assert catalog_instruction("full") in prompt
    assert REPLY in prompt
    assert assembly.diagnostics["rich_replies"]["instruction_tokens"] == catalog_instruction_tokens("full")
    assert rendered.diagnostics.estimated_tokens - plain.diagnostics.estimated_tokens >= catalog_instruction_tokens("full")


def test_with_the_policy_false_prompts_are_byte_identical_to_today():
    disabled = RichReplyDecision(False, "full", "session_setting_off")
    _, rendered = _rendered(disabled)
    _, today = _rendered(None)

    assert [(m.role, m.content) for m in rendered.messages] == [(m.role, m.content) for m in today.messages]
    prompt = "\n".join(message.content for message in rendered.messages)
    assert "omnix-ui" not in prompt
    assert "Revenue held.\n\nRevenue: $6,930." in prompt


def test_character_sessions_never_get_the_instruction_even_if_asked():
    character = SimpleNamespace(
        interaction_mode="character", assistant_identity=["You are Maya."], model_dump=lambda **_kwargs: {"interaction_mode": "character"},
    )
    assembly, rendered = _rendered(
        RichReplyDecision(True, "full", "enabled"), session(interaction_mode="character"), identity_resolver=lambda _session: character,
    )

    assert all("omnix-ui" not in message.content for message in rendered.messages)
    assert assembly.diagnostics["rich_replies"]["enabled"] is False


def test_rich_replies_round_trips_through_the_session_settings_document():
    chat_session = session("on")
    settings = PostgresChatRepositoryAdapter._settings(chat_session)
    record = {"id": chat_session.id, "title": "GUI", "workspace_id": "workspace:default", "created_at": NOW, "updated_at": NOW, "settings": settings}

    assert settings["rich_replies"] == "on"
    assert PostgresChatRepositoryAdapter._summary_fields(record)["rich_replies"] == "on"
    assert PostgresChatRepositoryAdapter._summary_fields({**record, "settings": {}})["rich_replies"] is None
    assert PostgresChatRepositoryAdapter._summary_fields({**record, "settings": {"rich_replies": "maybe"}})["rich_replies"] is None


def test_the_route_sets_and_clears_the_setting_and_rejects_unknown_sessions(tmp_path):
    store = ChatSessionStore(tmp_path / "chat.json")
    created = store.create_session(CreateChatSessionRequest(title="GUI"))
    app = FastAPI()
    app.include_router(create_rich_replies_router(chat_store_factory=lambda: store))
    client = TestClient(app)

    response = client.post(f"/api/chat/sessions/{created.id}/rich-replies", json={"rich_replies": "on"})
    assert response.json() == {"ok": True, "session_id": created.id, "rich_replies": "on"}
    assert store.get_session(created.id).rich_replies == "on"

    response = client.post(f"/api/chat/sessions/{created.id}/rich-replies", json={"rich_replies": None})
    assert response.json()["rich_replies"] is None
    assert store.get_session(created.id).rich_replies is None

    assert client.post("/api/chat/sessions/chat:missing/rich-replies", json={"rich_replies": "on"}).status_code == 404
    assert client.post(f"/api/chat/sessions/{created.id}/rich-replies", json={"rich_replies": "maybe"}).status_code == 422
