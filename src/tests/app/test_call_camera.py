"""The call asks to look (companion roadmap 4.3): it can only ask; the person's press of Show opens the camera."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.platform.assistant_tools.owner_grants import ABILITIES, authorize
from app.platform.live_voice.llm import call_tools
from app.platform.live_voice.llm.call_tools import CAMERA_ASK_LINE, RequestGate, parse_request
from app.platform.live_voice.llm.stream import stream_low_latency_reply
from app.providers import ChatResponse


def test_look_is_its_own_verb_and_look_up_still_searches() -> None:
    look = parse_request("[[look: the label on the jar || Can you show me? Press Show.]]")
    lookup = parse_request("[[look up: weather in Paris || one sec]]")

    assert look == call_tools.AbilityRequest("camera", "the label on the jar", "Can you show me? Press Show.")
    assert not look.background
    assert lookup is not None and lookup.ability == "web_search"
    gate = RequestGate()
    assert gate.push("[[look: the jar") == ""  # markup is never read aloud


def test_the_camera_is_off_for_everyone_until_granted() -> None:
    camera = ABILITIES["camera"]
    assert (camera.default_system, camera.default_character) == (False, False)
    assert authorize("system", "camera", grants={}).reason == "not_granted"
    assert authorize("system", "camera", grants={"camera": True}).allowed


def test_the_prompt_offers_look_only_with_the_grant() -> None:
    assert "[[look:" in (call_tools.abilities_prompt({"camera": True}) or "")
    assert call_tools.abilities_prompt({"camera": False}) is None


def test_look_is_offered_only_when_a_picture_could_be_described(monkeypatch) -> None:
    monkeypatch.setattr(call_tools, "granted_abilities", lambda _s: {"camera": True})
    monkeypatch.setattr(call_tools, "camera_available", lambda: False)
    assert call_tools.offered_abilities(SimpleNamespace(id="chat:1")) == {"camera": False}
    monkeypatch.setattr(call_tools, "camera_available", lambda: True)
    assert call_tools.offered_abilities(SimpleNamespace(id="chat:1")) == {"camera": True}


# --- A spoken turn --------------------------------------------------------------------------


def _store() -> SimpleNamespace:
    rendered = SimpleNamespace(messages=[
        SimpleNamespace(role="system", content="You are the assistant.", per_turn=False),
        SimpleNamespace(role="user", content="What does this label say?", per_turn=False),
    ])
    return SimpleNamespace(
        build_provider_prompt=lambda session, user_message, context_items: (SimpleNamespace(diagnostics={}), rendered),
        _active_memory_metadata=lambda assembly, current_rendered: {},
        _active_history_metadata=lambda assembly: {},
    )


class _Provider:
    provider_name = "claude_cli"

    def __init__(self, *replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any):
        self.calls.append(kwargs)
        parts = self.replies.pop(0)
        return iter([ChatResponse(content=part, model="haiku") for part in parts]
                    + [ChatResponse(content="", model="haiku", finish_reason="stop")])


def _turn(monkeypatch, provider: _Provider, *, granted: bool, available: bool = True) -> list[dict[str, Any]]:
    monkeypatch.setattr(call_tools, "granted_abilities", lambda _session: {"camera": granted})
    monkeypatch.setattr(call_tools, "camera_available", lambda: available)
    monkeypatch.setattr("app.platform.live_voice.llm.stream._ability_gate", lambda _session: RequestGate())
    return list(stream_low_latency_reply(
        _store(), SimpleNamespace(id="chat:system", interaction_mode="system", character_id=None),
        SimpleNamespace(id="msg:user", content="What does this label say?", metadata={"speech_segment_id": "s-1"}),
        provider_id="llm:claude_cli", model_id=None, context_items=[], provider=provider,
    ))


def _spoken(events: list[dict[str, Any]]) -> str:
    return "".join(event["text"] for event in events if event["type"] == "text_chunk")


def test_a_granted_look_asks_and_ends_the_turn_with_a_camera_request(monkeypatch) -> None:
    provider = _Provider(["[[look: the label || Can you show me? Press", " Show.]]"])

    events = _turn(monkeypatch, provider, granted=True)

    assert _spoken(events) == "Can you show me? Press Show."
    assert len(provider.calls) == 1
    types = [event["type"] for event in events]
    assert types[-2:] == ["camera_request", "complete"]
    assert events[-2] == {"type": "camera_request", "what": "the label"}
    assert events[-1]["metadata"]["call_camera_request"] == {"query": "the label", "allowed": True,
                                                             "reason": "granted"}


def test_a_look_with_nothing_to_say_uses_the_fixed_ask(monkeypatch) -> None:
    events = _turn(monkeypatch, _Provider(["[[look: the label]]"]), granted=True)

    assert _spoken(events) == CAMERA_ASK_LINE


def test_a_look_without_the_grant_opens_nothing_and_the_model_says_it_cannot_see(monkeypatch) -> None:
    provider = _Provider(["[[look: the label || Show me.]]"], ["I can't see your camera, but read it to me?"])

    events = _turn(monkeypatch, provider, granted=False)

    assert "camera_request" not in [event["type"] for event in events]
    assert _spoken(events) == "I can't see your camera, but read it to me?"
    assert events[-1]["metadata"]["call_camera_request"]["reason"] == "not_granted"
    assert "cannot see their camera" in provider.calls[1]["messages"][-1].content


def test_a_granted_look_without_vision_is_recorded_unavailable(monkeypatch) -> None:
    provider = _Provider(["[[look: the label || Show me.]]"], ["I can't see right now."])

    events = _turn(monkeypatch, provider, granted=True, available=False)

    assert "camera_request" not in [event["type"] for event in events]
    assert events[-1]["metadata"]["call_camera_request"] == {"query": "the label", "allowed": False,
                                                             "reason": "unavailable"}
