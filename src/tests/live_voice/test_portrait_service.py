"""The live portrait service's contract, with a fake model (roadmap: docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md)."""
from __future__ import annotations

import hashlib
import io
import secrets
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.conversation.portrait_stream_contract import QUALITY_LEVELS, pack, unpack
from services.portrait import portrait_server
from services.portrait.portrait_image import PortraitImageError
from services.portrait.scheduler import PassPlan, linear_resample
from tests.support.waiting import wait_until

IMAGE = b"portrait image bytes"
IMAGE_SHA = hashlib.sha256(IMAGE).hexdigest()


class FakeSession:
    def __init__(self) -> None:
        self.passes: list[PassPlan] = []
        self.level = 0

    def run_pass(self, audio, plan: PassPlan, seed: int) -> None:
        self.passes.append(plan)

    def decode(self, start: int, stop: int) -> list[bytes | None]:
        step = QUALITY_LEVELS[self.level][1]
        return [f"jpeg-{index}-l{self.level}".encode() if index % step == 0 else None for index in range(start, stop)]

    def reset(self) -> None:
        pass

    def rewind(self, frames: int) -> None:
        pass

    def transition(self) -> list[bytes]:
        return [b"transition-0", b"transition-1"]

    def spawn(self) -> FakeSession:
        return FakeSession()


class FakeRuntime:
    resample = staticmethod(linear_resample)

    def __init__(self, engine: str = "float") -> None:
        self.engine = engine
        self.portraits: dict[str, object] = {}
        self.sessions: list[FakeSession] = []

    def prepare(self, key: str, payload: bytes) -> object:
        if payload == b"no face here":
            raise PortraitImageError("no_face", "No face was found in the portrait image")
        self.portraits[key] = SimpleNamespace(idle_jpegs={}, blink_jpegs={})
        return self.portraits[key]

    def portrait(self, key: str) -> object | None:
        return self.portraits.get(key)

    def forget(self, key: str) -> None:
        self.portraits.pop(key, None)

    def session(self, portrait: object, emotion: str) -> FakeSession:
        self.sessions.append(FakeSession())
        return self.sessions[-1]

    # As float_runtime.FloatRuntime: each level's loop and blink twins are cached on the portrait, and a level counts
    # as rendered only with both.
    def idle_frames(self, portrait: Any, level: int = 0) -> list[bytes]:
        return portrait.idle_jpegs.setdefault(level, [f"idle-{index}-l{level}".encode() for index in range(3)])

    def blink_frames(self, portrait: Any, level: int = 0) -> list[bytes]:
        return portrait.blink_jpegs.setdefault(level, [f"blink-{index}-l{level}".encode() for index in range(3)])

    @staticmethod
    def rendered_idle_level(portrait: Any) -> int | None:
        return next((level for level in sorted(portrait.idle_jpegs) if level in portrait.blink_jpegs), None)


@pytest.fixture
def token(monkeypatch) -> str:
    value = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", value)
    return value


def _client(app, token: str | None) -> TestClient:
    headers = {"X-Omnix-Client": "test", **({"X-Omnix-Service-Token": token} if token else {})}
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000), headers=headers)


def _ready_app(runtime: FakeRuntime, **options):
    app = portrait_server.create_app(load=lambda _engine: runtime, installed=lambda _engine: (True, ""),
                                     resources=lambda _engine: (True, ""), preload=False, **options)
    app.state.host.ensure_loading()
    if wait_until(lambda: app.state.host.status == "ready", bool, timeout=2, interval=0.01):
        return app
    raise AssertionError("the fake runtime did not load")


def _prepare(client: TestClient, tenant: str = "tenant-a", image: bytes = IMAGE, engine: str | None = None) -> dict:
    data = {"tenant": tenant, "image_sha256": hashlib.sha256(image).hexdigest(), **({"engine": engine} if engine else {})}
    return client.post("/portrait/prepare", data=data, files={"file": ("portrait.png", io.BytesIO(image))}).json()


class CountingRuntime(FakeRuntime):
    """Counts what is rendered, optionally failing at it."""

    def __init__(self, fail_idle: bool = False) -> None:
        super().__init__()
        self.rendered: list[str] = []
        self.fail_idle = fail_idle

    def idle_frames(self, portrait: object, level: int = 0) -> list[bytes]:
        if self.fail_idle:
            raise RuntimeError("no idle loop")
        self.rendered.append(f"idle-l{level}")
        return super().idle_frames(portrait, level)

    def blink_frames(self, portrait: object, level: int = 0) -> list[bytes]:
        self.rendered.append(f"blink-l{level}")
        return super().blink_frames(portrait, level)


def test_preparing_a_portrait_renders_its_idle_loop_so_a_call_finds_it_ready(token: str) -> None:
    runtime = CountingRuntime()
    with _client(_ready_app(runtime), token) as client:
        assert _prepare(client)["ok"] is True

    assert runtime.rendered == ["idle-l0", "blink-l0"]


class BlinkSearchingRuntime(CountingRuntime):
    """As flashhead_runtime.FlashHeadRuntime: looks for a blink in more silent renders when asked."""

    def find_blink(self, portrait: object) -> None:
        self.rendered.append("find-blink")


def test_preparing_a_flashhead_portrait_looks_for_its_blink_before_its_twins(token: str) -> None:
    # Owner report 2026-11-21: FlashHead's idle loop looked like a still image; its loop render often has no blink.
    runtime = BlinkSearchingRuntime()
    with _client(_ready_app(runtime), token) as client:
        assert _prepare(client)["ok"] is True
    assert runtime.rendered == ["idle-l0", "find-blink", "blink-l0"]


def test_between_speakers_neither_prepare_nor_idle_renders_a_loop_when_asked_not_to(token: str) -> None:
    # The review of 2026-11-20: a speaker swap leaves no stream open for a moment, and a member's idle loop asked
    # for then was rendered on the GPU thread ahead of the next speaker's frames.
    runtime = CountingRuntime()
    with _client(_ready_app(runtime), token) as client:
        prepared = client.post("/portrait/prepare", data={"tenant": "tenant-a", "image_sha256": IMAGE_SHA,
                                                          "render_idle": "false"},
                               files={"file": ("portrait.png", io.BytesIO(IMAGE))}).json()
        assert prepared["ok"] is True
        body = client.post("/portrait/idle", data={"latent_key": prepared["latent_key"], "rendered_only": "true"})
        assert body.json()["code"] == "portrait_busy"
    assert runtime.rendered == []


def test_a_portrait_is_still_prepared_when_its_idle_loop_cannot_be_rendered(token: str) -> None:
    with _client(_ready_app(CountingRuntime(fail_idle=True)), token) as client:
        assert _prepare(client)["ok"] is True


def test_preparing_during_a_call_leaves_the_gpu_to_the_call(token: str) -> None:
    runtime = CountingRuntime()
    client = _client(_ready_app(runtime), token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, latent_key)["type"] == "ready"
        _frames(websocket, 6)  # the call's own idle loop and blink
        runtime.rendered.clear()
        assert _prepare(client)["ok"] is True
        assert runtime.rendered == []


def _open(websocket, latent_key: str, call_key: str = "call-1", principal: str = "user-1", session: str = "s-1",
          level: int = 0) -> dict:
    websocket.send_json({"type": "open", "call_key": call_key, "principal": principal, "session": session,
                         "latent_key": latent_key, "emotion": "neutral", "level": level})
    return websocket.receive_json()


def _speak(websocket, output_id: str = "out-1", epoch: int = 3, segment_id: str = "seg-a") -> None:
    """One second of 24 kHz audio as one phrase, then the output's end."""
    websocket.send_json({"type": "phrase_start", "output_id": output_id, "epoch": epoch, "segment_id": segment_id,
                         "sample_rate": 24_000})
    pcm = (np.sin(np.arange(24_000) / 5.0) * 9000).astype("<i2")
    for offset in range(0, len(pcm), 4_800):
        websocket.send_bytes(pack({"segment_id": segment_id, "offset": offset}, pcm[offset:offset + 4_800].tobytes()))
    websocket.send_json({"type": "phrase_done", "segment_id": segment_id})
    websocket.send_json({"type": "output_end", "output_id": output_id, "epoch": epoch})


def _frames(websocket, count: int) -> tuple[list[tuple[dict, bytes]], list[tuple[dict, bytes]]]:
    """``count`` frames, split into the idle loop's (and its blink's) and the speech's (the two may interleave)."""
    frames = [unpack(websocket.receive_bytes()) for _ in range(count)]
    idle = [frame for frame in frames if frame[0]["output_id"] in {"idle", "blink"}]
    return idle, [frame for frame in frames if frame[0]["output_id"] not in {"idle", "blink"}]


def test_health_is_public_and_says_why_the_model_is_not_ready(token: str) -> None:
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda _engine: (False, "Install float"),
                                     resources=lambda _engine: (True, ""), preload=False)
    client = _client(app, None)
    assert client.get("/health").json()["status"] == "unloaded"
    authed = _client(app, token)
    assert authed.post("/portrait/prepare", data={"tenant": "t", "image_sha256": IMAGE_SHA},
                       files={"file": ("p.png", io.BytesIO(IMAGE))}).json() == {
        "ok": False, "code": "model_missing", "message": "Install float"}
    assert client.get("/health").json()["status"] == "missing"


def test_a_short_gpu_is_reported_and_not_loaded(token: str) -> None:
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda _engine: (True, ""),
                                     resources=lambda _engine: (False, "needs 2.5 GB"), preload=False)
    assert _prepare(_client(app, token))["code"] == "model_busy"
    assert app.state.host.status == "short"


def test_a_failing_load_check_is_reported_not_fatal(token: str) -> None:
    def broken(_engine: str) -> tuple[bool, str]:
        raise ModuleNotFoundError("httpx")

    app = portrait_server.create_app(load=FakeRuntime, installed=lambda _engine: (True, ""), resources=broken, preload=True)
    with _client(app, token) as client:  # runs the startup hook, which starts loading
        health = client.get("/health").json()
    assert health["status"] == "failed" and "ModuleNotFoundError" in health["message"]


def test_prepare_needs_the_service_token_and_the_images_digest(token: str) -> None:
    app = _ready_app(FakeRuntime())
    assert _client(app, None).post("/portrait/prepare", data={"tenant": "t", "image_sha256": IMAGE_SHA},
                                   files={"file": ("p.png", io.BytesIO(IMAGE))}).status_code == 401
    client = _client(app, token)
    assert client.post("/portrait/prepare", data={"tenant": "t", "image_sha256": "0" * 64},
                       files={"file": ("p.png", io.BytesIO(IMAGE))}).status_code == 400


def test_an_encoding_is_keyed_by_tenant_and_image_and_can_be_forgotten(token: str) -> None:
    runtime = FakeRuntime()
    client = _client(_ready_app(runtime), token)
    first = _prepare(client)
    assert first["ok"] and len(first["latent_key"]) == 64
    assert _prepare(client)["latent_key"] == first["latent_key"]
    assert _prepare(client, tenant="tenant-b")["latent_key"] != first["latent_key"]
    assert _prepare(client, image=b"no face here") == {
        "ok": False, "code": "no_face", "message": "No face was found in the portrait image"}
    assert client.delete(f"/portrait/cache/tenant-a/{IMAGE_SHA}").json() == {"ok": True}
    assert first["latent_key"] not in runtime.portraits


def test_the_stream_needs_the_service_token(token: str) -> None:
    client = _client(_ready_app(FakeRuntime()), None)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
            websocket.receive_json()


def test_a_stream_for_an_unprepared_portrait_is_refused(token: str) -> None:
    client = _client(_ready_app(FakeRuntime()), token)
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, "f" * 64)["code"] == "portrait_not_prepared"


def test_audio_in_frames_out_stamped_by_segment_and_offset(token: str) -> None:
    runtime = FakeRuntime()
    client = _client(_ready_app(runtime), token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, latent_key) == {"type": "ready"}
        _speak(websocket)
        idle, frames = _frames(websocket, 3 + 3 + 25)
    assert len(idle) == 3 + 3
    headers = [header for header, _jpeg in frames]
    assert [jpeg for _header, jpeg in frames] == [f"jpeg-{index}-l0".encode() for index in range(25)]
    assert {(header["output_id"], header["epoch"], header["segment_id"]) for header in headers} == {("out-1", 3, "seg-a")}
    assert [header["offset"] for header in headers[:3]] == [0, 960, 1920]


def test_the_idle_loop_follows_ready_at_the_opening_level(token: str) -> None:
    client = _client(_ready_app(FakeRuntime()), token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, latent_key, level=2) == {"type": "ready"}
        idle, speech = _frames(websocket, 3 + 3)
    assert speech == []
    assert [header for header, _jpeg in idle] == [
        {"output_id": "idle", "epoch": 0, "segment_id": "idle", "offset": index, "count": 3, "frame_ms": 80}
        for index in range(3)] + [  # then each loop frame with its eyes shut
        {"output_id": "blink", "epoch": 0, "segment_id": "blink", "offset": index, "count": 3, "frame_ms": 80}
        for index in range(3)]
    assert [jpeg for _header, jpeg in idle] == [f"idle-{index}-l2".encode() for index in range(3)] + [
        f"blink-{index}-l2".encode() for index in range(3)]


def test_a_quality_change_takes_effect_on_the_next_frames(token: str) -> None:
    client = _client(_ready_app(FakeRuntime()), token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, latent_key)["type"] == "ready"
        websocket.send_json({"type": "quality", "level": 3})
        _speak(websocket)
        _idle, frames = _frames(websocket, 3 + 3 + 13)  # every other frame of 25 at level 3
    assert [jpeg for _header, jpeg in frames] == [f"jpeg-{index}-l3".encode() for index in range(0, 25, 2)]
    assert portrait_server.quality_level(9) == 3 and portrait_server.quality_level("x") == 0


def test_one_stream_per_gpu_and_a_reload_replaces_its_own_stream(token: str) -> None:
    client = _client(_ready_app(FakeRuntime()), token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as first:
        assert _open(first, latent_key)["type"] == "ready"
        with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as other_call:
            refused = _open(other_call, latent_key, call_key="call-2", principal="user-2", session="s-2")
            assert refused["code"] == "portrait_busy"
        with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as reloaded:
            assert _open(reloaded, latent_key, call_key="call-3")["type"] == "ready"
            with pytest.raises(WebSocketDisconnect) as closed:
                while True:  # its idle loop, then the close
                    first.receive_bytes()
            assert closed.value.code == 4000


def test_leases_expire_without_heartbeats() -> None:
    admission = portrait_server.Admission(max_streams=1, timeout_seconds=0.05)
    first = portrait_server.Lease("call-1", "user-1", "s-1", websocket=None)  # type: ignore[arg-type]
    assert admission.admit(first) == (True, [])
    assert admission.admit(portrait_server.Lease("call-2", "user-2", "s-2", websocket=None))[0] is False  # type: ignore[arg-type]
    time.sleep(0.08)
    assert admission.expired() == [first] and admission.active == 0


def test_an_idle_model_unloads_only_with_no_stream_open() -> None:
    host = portrait_server.RuntimeHost(FakeRuntime, lambda _engine: (True, ""), lambda _engine: (True, ""))
    host.ensure_loading()
    wait_until(lambda: host.status == "ready", bool, timeout=2, interval=0.01)
    assert not host.unload_if_idle(0.0, active_streams=1)
    assert host.unload_if_idle(0.0, active_streams=0) and host.status == "unloaded"


def test_the_model_loads_on_demand(monkeypatch, token: str) -> None:
    monkeypatch.setattr(portrait_server, "free_vram_gb", lambda: 8.0)
    monkeypatch.delenv("OMNIX_PORTRAIT_PRELOAD", raising=False)
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda _engine: (True, ""), resources=lambda _engine: (True, ""))
    with _client(app, token) as client:  # runs the startup hook: nothing loads
        assert client.get("/health").json()["status"] == "unloaded"
        assert _prepare(client).get("code") in {"warming", None}  # a call's prepare starts the load
        wait_until(lambda: app.state.host.status == "ready", bool, timeout=2, interval=0.01)
        assert _prepare(client)["ok"] is True
        assert client.get("/health").json()["gpu"] == {"vram_free_bytes": 8 * 1024**3}


def test_the_load_check_never_asks_cuda(monkeypatch) -> None:
    # Review finding (2026-10-31): the check asked CUDA for free memory, which created the context (about 2.5 GB)
    # the light process is meant not to hold, and a check that found too little kept it for good.
    import sys
    import types

    def refuse() -> None:
        raise AssertionError("CUDA was asked")

    fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(mem_get_info=refuse, is_available=refuse,
                                                                  is_initialized=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(portrait_server, "free_vram_gb", lambda: 1.0)
    fits, why = portrait_server._default_resources("float")
    assert not fits and "VRAM" in why


def test_an_unloaded_idle_model_asks_its_launcher_to_start_the_service_again_light(token: str) -> None:
    from app.runtime.process_control import IDLE_EXIT_CODE

    app = _ready_app(FakeRuntime(), idle_unload_seconds=0.0)
    exits: list[int] = []
    app.state.request_exit = exits.append
    with _client(app, token):  # the housekeeping task runs once a second
        wait_until(lambda: exits, bool, timeout=3, interval=0.01)
    assert exits == [IDLE_EXIT_CODE] and app.state.host.status == "exiting"  # nothing loads before it exits


def test_unload_on_request_exits_light_but_never_under_a_call_or_mid_load(token: str, monkeypatch) -> None:
    from app.runtime.process_control import IDLE_EXIT_CODE

    app = _ready_app(FakeRuntime())
    exits: list[int] = []
    app.state.request_exit = exits.append
    with _client(app, token) as client:
        with monkeypatch.context() as patched:
            patched.setattr(portrait_server.Admission, "active", property(lambda _self: 1))  # a call's stream
            assert client.post("/portrait/unload").json()["code"] == "model_busy"
        app.state.host.status = "warming"
        assert client.post("/portrait/unload").json()["code"] == "warming"
        app.state.host.status = "ready"
        assert client.post("/portrait/unload").json() == {"ok": True, "status": "exiting"}
    assert exits == [IDLE_EXIT_CODE] and app.state.host.runtime is None


def test_unload_without_a_launcher_drops_the_model_in_place(token: str) -> None:
    app = _ready_app(FakeRuntime())
    with _client(app, token) as client:
        assert client.post("/portrait/unload").json() == {"ok": True, "status": "unloaded"}
        assert client.post("/portrait/unload").json() == {"ok": True, "status": "unloaded"}  # nothing loaded: a no-op
    assert app.state.host.runtime is None


def test_an_exiting_service_loads_nothing_and_says_it_is_restarting() -> None:
    host = portrait_server.RuntimeHost(FakeRuntime, lambda _engine: (True, ""), lambda _engine: (True, ""))
    host.ensure_loading()
    wait_until(lambda: host.status == "ready", bool, timeout=2, interval=0.01)
    assert host.unload_if_idle(0.0, active_streams=0, exit_after=True) and host.status == "exiting"
    host.ensure_loading()  # a prepare in the moments before the process exits
    assert host.status == "exiting"
    with pytest.raises(portrait_server.Unavailable) as refused:
        host.get()
    assert refused.value.code == "service_unreachable"  # the gateway waits for the restart
    assert host.ready_runtime() is None


def test_a_failed_load_that_woke_cuda_exits_once_idle(monkeypatch) -> None:
    def broken(_engine: str) -> object:
        raise RuntimeError("no")

    host = portrait_server.RuntimeHost(broken, lambda _engine: (True, ""), lambda _engine: (True, ""))
    host.ensure_loading()
    wait_until(lambda: host.status == "failed", bool, timeout=2, interval=0.01)
    monkeypatch.setattr(portrait_server, "_cuda_initialized", lambda: False)
    assert not host.unload_if_idle(0.0, active_streams=0, exit_after=True)  # nothing held: stay up
    monkeypatch.setattr(portrait_server, "_cuda_initialized", lambda: True)
    assert not host.unload_if_idle(0.0, active_streams=0)  # no launcher to restart it: stay up
    assert host.unload_if_idle(0.0, active_streams=0, exit_after=True) and host.status == "exiting"


def test_a_preloaded_model_stays_loaded(token: str) -> None:
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda _engine: (True, ""), resources=lambda _engine: (True, ""),
                                     idle_unload_seconds=0.0, preload=True)
    exits: list[int] = []
    app.state.request_exit = exits.append
    with _client(app, token):
        time.sleep(1.5)  # past a housekeeping pass, idle all along
    assert exits == [] and app.state.host.status == "ready"


def test_a_stream_whose_session_fails_to_make_leaves_nothing_behind(token: str) -> None:
    # Review finding (2026-10-31): setup ran outside the cleanup, leaking the worker, its sender and the lease.
    class BrokenSessions(FakeRuntime):
        def session(self, portrait: object, emotion: str) -> FakeSession:
            raise RuntimeError("out of memory")

    app = _ready_app(BrokenSessions())
    client = _client(app, token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        websocket.send_json({"type": "open", "call_key": "c", "principal": "p", "session": "s",
                             "latent_key": latent_key, "emotion": "neutral", "level": 0})
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
    assert closed.value.code == 1011
    assert app.state.admission.active == 0 and app.state.host._workers == []


@pytest.mark.parametrize("message", [
    {"type": "phrase_start", "output_id": "o", "epoch": 1, "segment_id": "s", "sample_rate": 0},
    {"type": "phrase_start", "output_id": "o", "epoch": 1, "segment_id": "s"},
    {"type": "spec_prefix_end", "generation_id": "g", "segment_id": "s", "samples": -4},
    {"type": "cancel", "output_id": "o"},
    ["not", "an", "object"],
])
def test_a_malformed_control_message_closes_the_stream_and_cleans_up(token: str, message: object) -> None:
    app = _ready_app(FakeRuntime())
    client = _client(app, token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, latent_key) == {"type": "ready"}
        websocket.send_json(message)
        with pytest.raises(WebSocketDisconnect) as closed:
            while True:
                websocket.receive_bytes()
    assert closed.value.code == 1003
    wait_until(lambda: app.state.admission.active == 0 and not app.state.host._workers, bool, timeout=1, interval=0.01)
    assert app.state.admission.active == 0 and app.state.host._workers == []


def test_a_stream_whose_worker_fails_is_closed_without_waiting_for_a_message(token: str) -> None:
    class FailingSession(FakeSession):
        def run_pass(self, audio, plan: PassPlan, seed: int) -> None:
            raise RuntimeError("CUDA error")

    class FailingRuntime(FakeRuntime):
        def session(self, portrait: object, emotion: str) -> FakeSession:
            return FailingSession()

    app = _ready_app(FailingRuntime())
    client = _client(app, token)
    latent_key = _prepare(client)["latent_key"]
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, latent_key) == {"type": "ready"}
        _speak(websocket)
        with pytest.raises(WebSocketDisconnect) as closed:
            while True:
                websocket.receive_bytes()
    assert closed.value.code == 1011


def test_a_preview_gives_way_to_a_call_that_starts_while_it_renders() -> None:
    runtime = FakeRuntime()
    portrait = runtime.prepare("k", b"image")
    pcm = (np.sin(np.arange(24_000) / 5.0) * 9000).astype("<i2")
    with pytest.raises(portrait_server.PreviewAborted):
        portrait_server.render_preview(runtime, portrait, "neutral", pcm, 24_000, abort=lambda: True)
    assert portrait_server.render_preview(runtime, portrait, "neutral", pcm, 24_000)  # no call: it renders


def test_a_preview_renders_a_short_clip_and_is_refused_while_a_call_streams(token: str) -> None:
    import base64

    client = _client(_ready_app(FakeRuntime()), token)
    latent_key = _prepare(client)["latent_key"]
    pcm = (np.sin(np.arange(24_000) / 5.0) * 9000).astype("<i2").tobytes()

    def preview(audio: bytes = pcm) -> dict:
        return client.post("/portrait/preview", data={"latent_key": latent_key, "emotion": "happy",
                                                      "sample_rate": "24000"},
                           files={"file": ("audio.pcm", io.BytesIO(audio))}).json()

    body = preview()
    assert body["ok"] and body["fps"] == 25
    assert [base64.b64decode(frame) for frame in body["frames"]] == [f"jpeg-{index}-l0".encode() for index in range(25)]
    assert client.post("/portrait/preview", data={"latent_key": latent_key, "sample_rate": "24000"},
                       files={"file": ("a.pcm", io.BytesIO(b"\x00" * (9 * 24_000 * 2)))}).status_code == 413
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, latent_key)["type"] == "ready"
        assert preview()["code"] == "portrait_busy"


def test_a_members_idle_loop_comes_back_as_rendered_and_is_never_rendered_during_a_call(token: str) -> None:
    import base64

    from services.portrait.idle_loop import idle_frame_step

    client = _client(_ready_app(FakeRuntime()), token)
    host_key = _prepare(client)["latent_key"]

    def idle(latent_key: str) -> dict:
        return client.post("/portrait/idle", data={"latent_key": latent_key}).json()

    body = idle(host_key)
    assert body["ok"] and body["frame_ms"] == 40 * idle_frame_step(0)
    assert [base64.b64decode(frame) for frame in body["idle"]] == [f"idle-{index}-l0".encode() for index in range(3)]
    assert [base64.b64decode(frame) for frame in body["blink"]] == [f"blink-{index}-l0".encode() for index in range(3)]
    assert idle("missing")["code"] == "portrait_not_prepared"
    with client.websocket_connect("/portrait/stream", headers={"Host": "127.0.0.1"}) as websocket:
        assert _open(websocket, host_key)["type"] == "ready"
        # A guest prepared during the call has no loop yet: rendering it would hold the call's frames back.
        guest_key = _prepare(client, image=b"another portrait")["latent_key"]
        assert idle(guest_key)["code"] == "portrait_busy"
        assert idle(host_key)["ok"] is True


def test_a_loop_whose_blink_was_never_rendered_is_not_ready_and_a_rendered_one_skips_the_gpu_thread(token) -> None:
    # The review of 2026-11-20: a loop counts as rendered only with its blink twins, and a rendered loop is read from
    # the portrait's cache, never queued on the GPU thread behind a call's steps.
    runtime = CountingRuntime()
    client = _client(_ready_app(runtime), token)
    prepared = client.post("/portrait/prepare", data={"tenant": "tenant-a", "image_sha256": IMAGE_SHA,
                                                      "render_idle": "false"},
                           files={"file": ("portrait.png", io.BytesIO(IMAGE))}).json()
    portrait = runtime.portrait(prepared["latent_key"])
    runtime.idle_frames(portrait, 0)  # the loop without its blink twins

    def idle(**fields) -> dict:
        return client.post("/portrait/idle", data={"latent_key": prepared["latent_key"], **fields}).json()

    assert idle(rendered_only="true")["code"] == "portrait_busy"
    runtime.rendered.clear()
    assert idle()["ok"] is True
    assert runtime.rendered == ["idle-l0", "blink-l0"]  # rendered on the GPU thread, once

    runtime.rendered.clear()

    def no_gpu(*_args, **_kwargs):
        raise AssertionError("a rendered loop went to the GPU thread")

    client.app.state.host.submit = no_gpu
    body = idle(rendered_only="true")
    assert body["ok"] is True and len(body["blink"]) == 3
    assert runtime.rendered == []


def _loaded_switching_app(monkeypatch, **options):
    monkeypatch.setattr(portrait_server, "_cuda_initialized", lambda: False)
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda _engine: (True, ""),
                                     resources=lambda _engine: (True, ""), **options)
    app.state.host.ensure_loading()
    wait_until(lambda: app.state.host.status == "ready", bool, timeout=2, interval=0.01)
    return app


def test_float_keys_are_unchanged_and_each_engine_keys_its_own_encodings() -> None:
    from app.models.catalog import load

    revision = load().model("float-code").revision
    before = hashlib.sha256(f"t\x00{IMAGE_SHA}\x00{revision}".encode()).hexdigest()  # the key before two engines
    assert portrait_server.portrait_key("t", IMAGE_SHA) == portrait_server.portrait_key("t", IMAGE_SHA, "float") == before
    assert portrait_server.portrait_key("t", IMAGE_SHA, "flashhead-lite") != before


def test_an_unknown_engine_is_refused(token: str) -> None:
    app = _ready_app(FakeRuntime())
    response = _client(app, token).post("/portrait/prepare", data={"tenant": "t", "image_sha256": IMAGE_SHA,
                                                                   "engine": "nope"},
                                        files={"file": ("p.png", io.BytesIO(IMAGE))})
    assert response.status_code == 400  # the service middleware hides the detail ("unknown_engine")


def test_the_other_engine_loads_in_place_when_the_service_may_not_exit(monkeypatch, token: str) -> None:
    app = _loaded_switching_app(monkeypatch, preload=False)
    client = _client(app, token)
    assert _prepare(client)["ok"] is True and app.state.host.runtime.engine == "float"
    assert _prepare(client, engine="flashhead-lite").get("code") in {"warming", None}
    wait_until(lambda: app.state.host.status == "ready", bool, timeout=2, interval=0.01)
    assert _prepare(client, engine="flashhead-lite")["ok"] is True
    assert app.state.host.runtime.engine == "flashhead-lite" and client.get("/health").json()["engine"] == "flashhead-lite"
    assert _prepare(client).get("code") in {"warming", None}  # no engine named: FLOAT, as before there were two
    wait_until(lambda: app.state.host.status == "ready", bool, timeout=2, interval=0.01)
    assert app.state.host.runtime.engine == "float"


def test_a_service_holding_cuda_exits_to_switch_engines(monkeypatch, token: str) -> None:
    from app.runtime.process_control import IDLE_EXIT_CODE

    app = _loaded_switching_app(monkeypatch, preload=False)
    exits: list[int] = []
    app.state.request_exit = exits.append
    client = _client(app, token)
    assert _prepare(client, engine="flashhead-lite")["code"] == "service_unreachable"  # the gateway waits it out
    assert exits == [IDLE_EXIT_CODE] and app.state.host.status == "exiting" and app.state.host.runtime is None
    assert _prepare(client)["code"] == "service_unreachable"  # nothing loads before it exits


def test_a_preloaded_service_switches_in_place_never_by_a_restart(monkeypatch, token: str) -> None:
    app = _loaded_switching_app(monkeypatch, preload=True)
    exits: list[int] = []
    app.state.request_exit = exits.append
    assert _prepare(_client(app, token), engine="flashhead-lite").get("code") in {"warming", None}
    wait_until(lambda: app.state.host.status == "ready", bool, timeout=2, interval=0.01)
    assert exits == [] and app.state.host.runtime.engine == "flashhead-lite"


def test_engines_do_not_switch_under_a_call_or_a_load(monkeypatch, token: str) -> None:
    app = _loaded_switching_app(monkeypatch, preload=False)
    client = _client(app, token)
    host = app.state.host
    host._workers.append(SimpleNamespace(step=lambda: None))
    # Not "model_busy": the gateway waits that one out for the whole call, as too little memory.
    assert _prepare(client, engine="flashhead-lite")["code"] == "engine_in_use"
    host._workers.clear()
    host.status = "warming"
    assert _prepare(client, engine="flashhead-lite")["code"] == "warming"
    assert host.engine == "float"


def test_engines_do_not_switch_between_a_calls_streams(monkeypatch, token: str) -> None:
    # Review 2026-11-22: a group call replaces its stream at each speaker change, so the service is briefly without
    # one; an engine changed in Settings meanwhile ended the call's video (the process exits to switch).
    from services.portrait import portrait_server

    app = _loaded_switching_app(monkeypatch, preload=False)
    exits: list[int] = []
    app.state.request_exit = exits.append
    client = _client(app, token)
    admission = app.state.admission
    lease = portrait_server.Lease("call-1", "local", "chat-1", SimpleNamespace())
    assert admission.admit(lease)[0] is True
    assert _prepare(client, engine="flashhead-lite")["code"] == "engine_in_use"  # a stream is open
    admission.release(lease)
    assert _prepare(client, engine="flashhead-lite")["code"] == "engine_in_use"  # between two speakers
    assert exits == [] and app.state.host.engine == "float"
    monkeypatch.setattr(portrait_server, "ENGINE_SWITCH_GRACE_SECONDS", 0.0)
    assert _prepare(client, engine="flashhead-lite")["code"] == "service_unreachable"  # the call is over: it switches
    assert exits
