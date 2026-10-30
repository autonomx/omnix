"""The live-call TTS websocket's portrait copy (roadmap: docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 2)."""
from __future__ import annotations

from typing import Any

from tests.app.test_gateway_tts_live_call_websocket import FakeTtsProvider, _configure_gateway, _request


class FakeLink:
    """Records what the TTS route copies to the portrait service."""

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.closed = False

    def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def send_pcm(self, segment_id: str, offset: int, pcm: bytes) -> None:
        self.sent.append(("pcm", segment_id, offset, len(pcm)))

    async def close(self) -> None:
        self.closed = True


def _owned_request(text: str, phrase_index: int) -> dict[str, Any]:
    return {**_request(text, phrase_index), "output_id": "out-1", "generation_epoch": 2,
            "segment_id": f"seg-{phrase_index}", "output_order": phrase_index}


def test_without_a_portrait_request_nothing_changes(monkeypatch) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(_owned_request("Hello there.", 0))
        assert websocket.receive_json()["type"] == "start"
        websocket.receive_bytes()
        websocket.receive_json()
        assert len(client.app.state.live_portrait_calls) == 0


def test_a_portrait_call_gets_a_hello_and_its_audio_is_copied_with_offsets(monkeypatch) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    calls = client.app.state.live_portrait_calls
    link = FakeLink()
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello" and hello["call_key"] and hello["avatar_token"]
        assert calls.claim(hello["avatar_token"], "someone-else") is None
        call = calls.claim(hello["avatar_token"], "local")
        assert call is not None and call.call_key == hello["call_key"]
        call.attach(link)

        websocket.send_json(_owned_request("First phrase.", 0))
        assert websocket.receive_json()["type"] == "start"
        frame = websocket.receive_bytes()
        assert websocket.receive_json()["type"] == "done"
        websocket.send_json(_owned_request("Second phrase.", 1))
        websocket.receive_json()
        websocket.receive_bytes()
        websocket.receive_json()
        websocket.send_json({"type": "output_end", "output_id": "out-1", "generation_epoch": 2})
        websocket.send_json({"type": "cancel", "output_id": "out-1", "generation_epoch": 2, "segment_id": "seg-1"})
        assert websocket.receive_json()["type"] == "cancel_accepted"
        websocket.send_json({"type": "close", "reason": "finished"})

    # The portrait's output is the turn (its generation), whatever each phrase's own output id is.
    phrase = [
        {"type": "tts_priority", "on": True},
        {"type": "phrase_start", "output_id": "turn-2", "epoch": 2, "segment_id": "seg-0", "sample_rate": 24_000},
        ("pcm", "seg-0", 0, len(frame)),
        {"type": "tts_priority", "on": False},
        {"type": "phrase_done", "segment_id": "seg-0"},
    ]
    assert link.sent[:5] == phrase
    assert link.sent[5:10] == [{"type": "tts_priority", "on": True},
                               {**phrase[1], "segment_id": "seg-1"},
                               ("pcm", "seg-1", 0, len(frame)),
                               {"type": "tts_priority", "on": False},
                               {"type": "phrase_done", "segment_id": "seg-1"}]
    assert link.sent[10:] == [{"type": "output_end", "output_id": "turn-2", "epoch": 2},
                              {"type": "cancel", "output_id": "turn-2", "epoch": 2}]
    # The call is over: it leaves the registry and its portrait link is closed.
    assert len(calls) == 0 and link.closed


def test_pcm_offsets_count_each_phrases_own_samples() -> None:
    from app.platform.live_voice.portrait.calls import PortraitCalls

    call = PortraitCalls().issue("local")
    link = FakeLink()
    call.attach(link)
    call.phrase_start("out", 1, "seg", 24_000)
    for _ in range(3):
        call.pcm("seg", b"\x00\x00" * 960)
    call.phrase_done("seg")
    assert [item[2] for item in link.sent if isinstance(item, tuple)] == [0, 960, 1920]
