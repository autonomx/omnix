"""Live narration drafts: the prose so far from a partly written answer, scoped to the turn's user (no database)."""
from __future__ import annotations

import json

from app.apps.rpg.narration import narration_drafts
from app.apps.rpg.narration.narration_drafts import (
    draft_text_from_partial_json,
    narration_draft_active,
    narration_draft_context,
    publish_narration_draft,
    read_narration_draft,
)
from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant

ANSWER = json.dumps({
    "blocks": [
        {"beat_id": "b1", "text": "The forge rings.", "claims": [{"claim_id": "c1", "text": "CLAIM"}]},
        {"beat_id": "b2", "speaker_id": "npc:orik", "text": 'Welcome, "friend". Été is warm.'},
    ]
}, ensure_ascii=True)


def test_the_draft_is_each_blocks_prose_as_far_as_it_has_arrived() -> None:
    assert draft_text_from_partial_json("") == ""
    assert draft_text_from_partial_json(ANSWER[:30]) == ""
    assert draft_text_from_partial_json(ANSWER[:ANSWER.index("rings") + 2]) == "The forge ri"
    # A claim's text is not prose.
    middle = ANSWER[:ANSWER.index("b2")]
    assert draft_text_from_partial_json(middle) == "The forge rings."
    assert draft_text_from_partial_json(ANSWER) == 'The forge rings.\n\nWelcome, "friend". Été is warm.'
    # An escape that has not fully arrived is left out until it has.
    cut = ANSWER.index("\\u00c9") + 3
    assert draft_text_from_partial_json(ANSWER[:cut]).endswith('Welcome, "friend".')


def _tenant(user: str) -> TenantContext:
    return TenantContext(user_id=user, workspace_id="workspace:one", membership_id=f"m:{user}", roles=frozenset({"owner"}))


def test_a_draft_is_published_inside_its_turn_and_read_only_by_its_user() -> None:
    narration_drafts._DRAFTS.clear()
    token = push_tenant(_tenant("user:wren"))
    try:
        assert narration_draft_active() is False
        publish_narration_draft("ignored outside a turn")
        with narration_draft_context("rpg_1", "submit:abc"):
            assert narration_draft_active() is True
            publish_narration_draft("The forge rings.")
            assert read_narration_draft("rpg_1", "submit:abc") == {"text": "The forge rings.", "done": False, "found": True}
        assert read_narration_draft("rpg_1", "submit:abc")["done"] is True
        assert read_narration_draft("rpg_1", "submit:other")["found"] is False
    finally:
        pop_tenant(token)
    other = push_tenant(_tenant("user:mallory"))
    try:
        assert read_narration_draft("rpg_1", "submit:abc") == {"text": "", "done": False, "found": False}
    finally:
        pop_tenant(other)


def test_the_narrative_writer_streams_into_the_draft_and_returns_the_same_answer() -> None:
    from app.apps.rpg.narration.narrative_provider import _ConfiguredProviderView
    from app.providers.base import ChatResponse

    class CliLike:
        provider_name = "claude_cli"
        config = None

        def __init__(self) -> None:
            self.streamed: list[bool] = []

        def chat_completion(self, messages, stream=False, **kwargs):
            self.streamed.append(stream)
            if not stream:
                return ChatResponse(content=ANSWER, model="haiku", finish_reason="end_turn")
            pieces = [ANSWER[index:index + 7] for index in range(0, len(ANSWER), 7)]
            chunks = [ChatResponse(content="", model="haiku", raw_response={"structured_delta": piece}) for piece in pieces]
            return iter([*chunks, ChatResponse(content=ANSWER, model="haiku", finish_reason="end_turn")])

    narration_drafts._DRAFTS.clear()
    provider = CliLike()
    view = _ConfiguredProviderView(provider, "claude_cli")
    # Outside a turn's draft: a plain call.
    assert view.chat_completion([]).content == ANSWER and provider.streamed == [False]
    token = push_tenant(_tenant("user:wren"))
    try:
        with narration_draft_context("rpg_1", "submit:abc"):
            answer = view.chat_completion([])
            draft = read_narration_draft("rpg_1", "submit:abc")
    finally:
        pop_tenant(token)
    assert provider.streamed == [False, True]
    assert answer.content == ANSWER and answer.finish_reason == "end_turn"
    assert draft["text"] == 'The forge rings.\n\nWelcome, "friend". Été is warm.'
