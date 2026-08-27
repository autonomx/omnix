from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.chat_bridge import _direct_request, _select_profile
from app.agent_runtime.router import route_omnix_request


def test_direct_home_request_compiles_without_hermes() -> None:
    request = _direct_request(
        "Turn off the Desk Plug",
        session_id="chat-1",
        message_id="msg-1",
        capability_id="home.set_state",
    )
    assert request is not None
    assert request.action_id == "home.set_state"
    assert request.input == {"target": "Desk Plug", "state": "off"}
    assert request.proposal_id == "direct:chat-1:msg-1"


def test_open_ended_agentic_text_is_not_explicit_authority() -> None:
    decision = route_omnix_request("implement the missing feature")
    assert decision.lane == "agent"
    assert decision.explicit is False


def test_chat_profile_selection_is_semantic_and_bounded() -> None:
    assert _select_profile("fix the repository tests") == "coding"
    assert _select_profile("fix the trading UI") == "coding"
    assert _select_profile("turn off the kitchen plug") == "house"
    assert _select_profile("check my calendar") == "personal-assistant"
    assert _select_profile("research this stock") == "trading-research"
    assert _select_profile("investigate this topic") == "research"


def test_live_voice_metadata_can_be_detected_without_session_state() -> None:
    from app.agent_runtime.chat_bridge import _is_live_voice
    message = SimpleNamespace(metadata={"speech_segment_id": "voice-segment:abc"})
    assert _is_live_voice(message) is True
