"""Speculative TTS copied into a call's portrait (roadmap Phase 3, "Keeping the hold near zero")."""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.conversation.portrait_stream_contract import unpack
from app.platform.live_voice.portrait.calls import PortraitCall, PortraitCalls, SpeculativeCopy
from app.platform.live_voice.speech import speculative_tts
from app.platform.live_voice.speech.speculative_tts import (
    _accept_entry,
    _cancel_entry,
    _claim_entry,
    _LiveLaneProviderProxy,
    _start_prefetch,
    _stream_kwargs,
    clear_speculative_tts_cache,
    register_live_voice_execution_lane_routes,
)
from app.platform.live_voice.speech.tts_lane import reset_live_voice_execution_lane_for_tests
from app.platform.live_voice.transport.websocket import _advance_portrait_replay
from tests.live_voice.test_live_voice_speculative_tts import _BlockingProvider, _request


class FakeLink:
    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.closed = False

    def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def send_pcm(self, segment_id: str, offset: int, pcm: bytes) -> None:
        self.sent.append(("pcm", segment_id, offset, len(pcm) // 2))


class FakeCopy:
    """Records what the prefetch thread copies, and whether its entry's lock was held at the time."""

    def __init__(self, generation_id: str = "") -> None:
        self.chunks: list[int] = []
        self.dropped = 0
        self.usable = True
        self.lock_held: list[bool] = []
        self.generation_id = generation_id

    def chunk(self, pcm: bytes, sample_rate: int) -> None:
        self.chunks.append(len(pcm) // 2)
        entry = speculative_tts._ENTRIES.get(self.generation_id)
        self.lock_held.append(entry is not None and entry.condition._is_owned())  # type: ignore[attr-defined]

    def drop(self) -> None:
        self.dropped += 1


def _reset() -> None:
    clear_speculative_tts_cache()
    reset_live_voice_execution_lane_for_tests()


def _call() -> tuple[PortraitCall, FakeLink]:
    call, link = PortraitCall(call_key="call-1", token="token", principal="local"), FakeLink()
    call.link = link  # type: ignore[assignment]
    return call, link


def test_a_replayed_phrase_skips_what_the_prefetch_copied_and_sends_the_rest_after_the_prefix() -> None:
    call, link = _call()
    call.phrase_start("out", 4, "seg", 24_000)
    call.bind("gen-1", 4, "seg")
    call.pcm("seg", b"\x00\x00" * 960, ("gen-1", 960, False))
    call.pcm("seg", b"\x00\x00" * 960, ("gen-1", 1_400, True))  # the replay ended inside this block
    call.pcm("seg", b"\x00\x00" * 960, ("gen-1", 1_400, True))
    assert link.sent[1] == {"type": "spec_bind", "generation_id": "gen-1", "output_id": "turn-4", "epoch": 4,
                            "segment_id": "seg"}
    assert link.sent[2:] == [
        {"type": "spec_prefix_end", "generation_id": "gen-1", "segment_id": "seg", "samples": 1_400},
        ("pcm", "seg", 1_400, 520),
        ("pcm", "seg", 1_920, 960),
    ]


def test_a_phrase_that_is_all_replay_ends_its_prefix_when_done() -> None:
    call, link = _call()
    call.phrase_start("out", 4, "seg", 24_000)
    call.bind("gen-1", 4, "seg")
    call.pcm("seg", b"\x00\x00" * 960, ("gen-1", 960, False))
    call.phrase_done("seg")
    assert link.sent[-2:] == [
        {"type": "spec_prefix_end", "generation_id": "gen-1", "segment_id": "seg", "samples": 960},
        {"type": "phrase_done", "segment_id": "seg"},
    ]


def test_the_replay_ends_at_the_first_chunk_the_portrait_has_no_copy_of() -> None:
    copied = {"speculation_portrait_copy": True, "speculation_generation_id": "gen-1"}
    replay = _advance_portrait_replay(None, copied, 480)
    replay = _advance_portrait_replay(replay, copied, 480)
    assert replay == ("gen-1", 960, False)
    replay = _advance_portrait_replay(replay, {"chunk": 9}, 480)
    assert replay == ("gen-1", 960, True)
    assert _advance_portrait_replay(replay, copied, 480) == ("gen-1", 960, True)
    assert _advance_portrait_replay(None, {"speculative_tts_cache": True}, 480) is None


def test_a_speculative_copy_reaches_the_portrait_on_the_calls_loop_and_is_dropped_when_it_falls_behind() -> None:
    async def scenario() -> list[Any]:
        call, link = _call()
        copy = SpeculativeCopy(call, "gen-1", asyncio.get_running_loop(), pending_limit=2)
        worker = threading.Thread(target=lambda: [copy.chunk(b"\x00\x00" * 480, 24_000) for _ in range(3)])
        worker.start()
        worker.join()
        await asyncio.sleep(0.01)
        assert copy.usable is False  # the third chunk found two still pending
        copy.drop()
        await asyncio.sleep(0.01)
        return link.sent

    sent = asyncio.run(scenario())
    assert sent[0] == {"type": "spec_start", "generation_id": "gen-1", "sample_rate": 24_000}
    assert [item for item in sent if isinstance(item, tuple)] == [("pcm", "spec:gen-1", 0, 480),
                                                                    ("pcm", "spec:gen-1", 480, 480)]
    assert sent.count({"type": "spec_drop", "generation_id": "gen-1"}) == 2


def test_the_prefetch_thread_copies_each_chunk_under_the_entry_lock_and_claims_stay_in_their_call() -> None:
    _reset()
    provider = _BlockingProvider()
    request = _request("Only this call may use this.")
    copy = FakeCopy("spec-call")
    try:
        _start_prefetch("spec-call", request, provider, "shared", call_key="call-1", portrait=copy)
        assert provider.first_chunk_ready.wait(timeout=1)
        _accept_entry("spec-call")
        kwargs = _stream_kwargs(request, provider)
        assert _claim_entry(request.text, request.speaker, request.language or "en", kwargs, "call-2") is None
        replay = _LiveLaneProviderProxy(provider, "shared").generate_audio_stream(
            text=request.text, speaker=request.speaker, language=request.language or "en",
            portrait_call_key="call-1", **kwargs)
        _pcm, _rate, timing = next(replay)
        assert timing["speculation_portrait_copy"] is True
        provider.allow_finish.set()
        list(replay)
        assert copy.chunks == [4_800, 4_800] and all(copy.lock_held)
        assert copy.dropped == 0
    finally:
        provider.allow_finish.set()
        _reset()


def test_every_way_an_entry_is_dropped_drops_its_portrait_copy() -> None:
    _reset()
    provider = _BlockingProvider()
    copies = [FakeCopy() for _ in range(3)]
    try:
        _start_prefetch("spec-a", _request("First."), provider, "shared", portrait=copies[0])
        _start_prefetch("spec-a", _request("First again."), provider, "shared", portrait=copies[1])
        assert copies[0].dropped == 1  # replaced
        assert _cancel_entry("spec-a") and copies[1].dropped == 1  # cancelled
        _start_prefetch("spec-b", _request("Second."), provider, "shared", portrait=copies[2])
        clear_speculative_tts_cache()
        assert copies[2].dropped == 1  # cleared
    finally:
        provider.allow_finish.set()
        _reset()


def test_the_prefetch_route_refuses_another_principals_call(monkeypatch) -> None:
    _reset()
    provider = _BlockingProvider()
    monkeypatch.setattr(speculative_tts, "get_cached_live_tts_provider", lambda: provider)
    state = SimpleNamespace()
    calls = PortraitCalls()
    state.live_portrait_calls = calls
    mine = calls.issue("local")
    other = calls.issue("someone-else")
    router = APIRouter()
    register_live_voice_execution_lane_routes(router, state)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    body = {"request": _request("Prefetch for the call.").model_dump(mode="json")}
    try:
        refused = client.post("/api/live/speculation/tts-prefetch",
                              json={**body, "generation_id": "spec-x", "call_key": other.call_key})
        assert refused.status_code == 403
        accepted = client.post("/api/live/speculation/tts-prefetch",
                               json={**body, "generation_id": "spec-y", "call_key": mine.call_key})
        assert accepted.status_code == 200
        assert speculative_tts._ENTRIES["spec-y"].call_key == mine.call_key
        assert speculative_tts._ENTRIES["spec-y"].portrait is None  # this call has no portrait attached
    finally:
        provider.allow_finish.set()
        _reset()


def test_spec_segment_frames_unpack() -> None:
    # The service's speculative segment name and the gateway's agree.
    from services.portrait.scheduler import SPEC_PREFIX

    from app.platform.live_voice.portrait.calls import SPEC_SEGMENT_PREFIX

    assert SPEC_PREFIX == SPEC_SEGMENT_PREFIX
    assert unpack(b"\x00\x00\x00\x02{}") == ({}, b"")
