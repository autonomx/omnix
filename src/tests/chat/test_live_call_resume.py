"""Where was I? (D1): the unheard rest of a reply the person cut into, offered to the next spoken turn once."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.platform.chat import live_call_resume, scene as scene_module
from app.platform.chat.models import ChatMessage

REPLY = (
    "The trail starts behind the old mill, and the first mile is flat. "
    "After the bridge it climbs steeply for two miles, so bring water and start before nine if you want shade."
)
HEARD_END = REPLY.index("After the bridge")


def _reply(*, at: str = "2026-11-23T10:00:00+00:00", end: int | None = HEARD_END, status: str = "interrupted",
           speaker: str | None = None, content: str = REPLY) -> ChatMessage:
    metadata: dict[str, Any] = {"delivery_status": status, "visual_delivered_text_end": end or 0}
    if end is not None:
        metadata["context_delivered_text_end"] = end
    if speaker:
        metadata["speaker_character_id"] = speaker
    return ChatMessage(id="msg:reply", role="assistant", content=content, created_at=at, metadata=metadata)


def _turn(text: str = "Wait, which mill?", *, at: str = "2026-11-23T10:00:20+00:00") -> ChatMessage:
    return ChatMessage(id="msg:turn", role="user", content=text, created_at=at,
                       metadata={"speech_segment_id": "voice-segment:1"})


def _session(*messages: ChatMessage) -> Any:
    return SimpleNamespace(id="chat:1", messages=list(messages))


@pytest.fixture(autouse=True)
def _no_scene(monkeypatch):
    monkeypatch.setattr(scene_module, "prompt_scene", lambda _session: None)


def test_a_reply_cut_into_offers_what_was_not_heard():
    turn = _turn()
    question = ChatMessage(id="msg:q", role="user", content="Tell me about the trail.", created_at="2026-11-23T09:59:55+00:00")
    reply = live_call_resume.cut_off_reply(_session(question, _reply(), turn), turn)

    assert reply is not None
    assert reply.message_id == "msg:reply"
    assert reply.heard == "The trail starts behind the old mill, and the first mile is flat."
    assert reply.unheard.startswith("After the bridge it climbs steeply")
    prompt = live_call_resume.cut_off_reply_prompt(reply)
    assert '"After the bridge it climbs steeply' in prompt
    assert "as I was saying" in prompt and "Never repeat what they already heard" in prompt


def test_the_turn_need_not_be_in_the_chat_yet():
    # An early start builds its prompt for a user message that is not committed.
    assert live_call_resume.cut_off_reply(_session(_reply()), _turn()) is not None


@pytest.mark.parametrize("case", [
    "completed", "answered", "late", "nothing_heard", "little_left", "no_delivery",
])
def test_nothing_is_offered_once_the_moment_has_passed(case):
    turn = _turn()
    messages: list[ChatMessage] = [_reply()]
    if case == "completed":
        messages = [_reply(status="completed")]
    elif case == "answered":
        # Something already answered their aside: the last line is not the cut-off reply.
        messages.append(ChatMessage(id="msg:aside", role="assistant", content="The red one.", created_at="2026-11-23T10:00:10+00:00"))
    elif case == "late":
        turn = _turn(at="2026-11-23T10:05:00+00:00")
    elif case == "nothing_heard":
        messages = [_reply(end=0)]
    elif case == "little_left":
        messages = [_reply(end=len(REPLY) - 20)]
    elif case == "no_delivery":
        messages = [_reply(end=None)]
    assert live_call_resume.cut_off_reply(_session(*messages, turn), turn) is None


def test_a_long_rest_is_clipped_at_a_word_and_sound_tags_are_not_offered():
    long_reply = "First part heard here. " + "[laughs] " + "and then a great deal more to say " * 40
    reply = live_call_resume.cut_off_reply(_session(_reply(content=long_reply, end=len("First part heard here."))), _turn())

    assert reply is not None
    assert "[laughs]" not in reply.unheard
    assert len(reply.unheard) <= live_call_resume.MAX_UNHEARD_CHARS + 1
    assert reply.unheard.endswith("…") and not reply.unheard.endswith(" …")


def test_in_a_group_call_only_the_member_cut_off_picks_it_up(monkeypatch):
    host = SimpleNamespace(character_id="char:maya")

    def scene_speaking(speaker_id: str):
        return lambda _session: SimpleNamespace(host=host, speaker_id=speaker_id)

    cut_off_guest = _reply(speaker="char:bea")
    monkeypatch.setattr(scene_module, "prompt_scene", scene_speaking("char:bea"))
    assert live_call_resume.cut_off_reply(_session(cut_off_guest), _turn()) is not None
    monkeypatch.setattr(scene_module, "prompt_scene", scene_speaking("char:maya"))
    assert live_call_resume.cut_off_reply(_session(cut_off_guest), _turn()) is None
    assert live_call_resume.cut_off_reply(_session(_reply()), _turn()) is not None  # the host's own reply


def test_the_call_prompt_carries_it_per_turn_and_goes_on_without_it(monkeypatch):
    from app.platform.chat.contracts import RenderedPromptMessage
    from app.platform.live_voice import pipeline

    def prompt_for(session_messages):
        rendered = SimpleNamespace(
            messages=[RenderedPromptMessage(role="system", content="You are Maya."),
                      RenderedPromptMessage(role="assistant", content="The trail starts behind the old mill."),
                      RenderedPromptMessage(role="user", content="Wait, which mill?")],
            diagnostics=SimpleNamespace(estimated_tokens=10, section_tokens={}),
        )
        ctx = SimpleNamespace(rendered=rendered, assembly=SimpleNamespace(diagnostics={}),
                              session=_session(*session_messages), user_message=_turn())
        pipeline._add_cut_off_reply(ctx)
        return ctx

    ctx = prompt_for([_reply()])
    added = ctx.rendered.messages[1]
    assert (added.role, added.per_turn) == ("system", True)
    assert "After the bridge" in added.content
    assert ctx.assembly.diagnostics["live_voice_cut_off_reply"]["message_id"] == "msg:reply"
    assert ctx.rendered.diagnostics.section_tokens["live_voice_cut_off_reply"] > 0

    assert len(prompt_for([_reply(status="completed")]).rendered.messages) == 3

    def broken(_session):
        raise RuntimeError("scene store down")

    monkeypatch.setattr(scene_module, "prompt_scene", broken)
    assert len(prompt_for([_reply()]).rendered.messages) == 3  # the turn goes on without it
