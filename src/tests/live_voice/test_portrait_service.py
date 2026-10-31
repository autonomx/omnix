"""The live portrait service's contract, with a fake model (roadmap: docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md)."""
from __future__ import annotations

import hashlib
import io
import secrets
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.conversation.portrait_stream_contract import QUALITY_LEVELS, pack, unpack
from services.portrait import portrait_server
from services.portrait.portrait_image import PortraitImageError
from services.portrait.scheduler import PassPlan, linear_resample

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

    def transition(self) -> list[bytes]:
        return [b"transition-0", b"transition-1"]

    def spawn(self) -> FakeSession:
        return FakeSession()


class FakeRuntime:
    resample = staticmethod(linear_resample)

    def __init__(self) -> None:
        self.portraits: dict[str, object] = {}
        self.sessions: list[FakeSession] = []

    def prepare(self, key: str, payload: bytes) -> object:
        if payload == b"no face here":
            raise PortraitImageError("no_face", "No face was found in the portrait image")
        self.portraits[key] = object()
        return self.portraits[key]

    def portrait(self, key: str) -> object | None:
        return self.portraits.get(key)

    def forget(self, key: str) -> None:
        self.portraits.pop(key, None)

    def session(self, portrait: object, emotion: str) -> FakeSession:
        self.sessions.append(FakeSession())
        return self.sessions[-1]

    def idle_frames(self, portrait: object, level: int = 0) -> list[bytes]:
        return [f"idle-{index}-l{level}".encode() for index in range(3)]

    def blink_frames(self, portrait: object, level: int = 0) -> list[bytes]:
        return [f"blink-{index}-l{level}".encode() for index in range(3)]


@pytest.fixture
def token(monkeypatch) -> str:
    value = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", value)
    return value


def _client(app, token: str | None) -> TestClient:
    headers = {"X-Omnix-Client": "test", **({"X-Omnix-Service-Token": token} if token else {})}
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000), headers=headers)


def _ready_app(runtime: FakeRuntime, **options):
    app = portrait_server.create_app(load=lambda: runtime, installed=lambda: (True, ""),
                                     resources=lambda: (True, ""), preload=False, **options)
    app.state.host.ensure_loading()
    for _ in range(200):
        if app.state.host.status == "ready":
            return app
        time.sleep(0.01)
    raise AssertionError("the fake runtime did not load")


def _prepare(client: TestClient, tenant: str = "tenant-a", image: bytes = IMAGE) -> dict:
    return client.post("/portrait/prepare", data={"tenant": tenant, "image_sha256": hashlib.sha256(image).hexdigest()},
                       files={"file": ("portrait.png", io.BytesIO(image))}).json()


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
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda: (False, "Install float"),
                                     resources=lambda: (True, ""), preload=False)
    client = _client(app, None)
    assert client.get("/health").json()["status"] == "unloaded"
    authed = _client(app, token)
    assert authed.post("/portrait/prepare", data={"tenant": "t", "image_sha256": IMAGE_SHA},
                       files={"file": ("p.png", io.BytesIO(IMAGE))}).json() == {
        "ok": False, "code": "model_missing", "message": "Install float"}
    assert client.get("/health").json()["status"] == "missing"


def test_a_short_gpu_is_reported_and_not_loaded(token: str) -> None:
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda: (True, ""),
                                     resources=lambda: (False, "needs 2.5 GB"), preload=False)
    assert _prepare(_client(app, token))["code"] == "model_busy"
    assert app.state.host.status == "short"


def test_a_failing_load_check_is_reported_not_fatal(token: str) -> None:
    def broken() -> tuple[bool, str]:
        raise ModuleNotFoundError("httpx")

    app = portrait_server.create_app(load=FakeRuntime, installed=lambda: (True, ""), resources=broken, preload=True)
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
    host = portrait_server.RuntimeHost(FakeRuntime, lambda: (True, ""), lambda: (True, ""))
    host.ensure_loading()
    for _ in range(200):
        if host.status == "ready":
            break
        time.sleep(0.01)
    assert not host.unload_if_idle(0.0, active_streams=1)
    assert host.unload_if_idle(0.0, active_streams=0) and host.status == "unloaded"


def test_the_model_loads_on_demand_and_health_never_wakes_cuda_before(monkeypatch, token: str) -> None:
    import services.helper_models

    asked: list[str] = []
    monkeypatch.setattr(services.helper_models, "free_vram_gb", lambda: asked.append("vram") or 8.0)
    monkeypatch.delenv("OMNIX_PORTRAIT_PRELOAD", raising=False)
    app = portrait_server.create_app(load=FakeRuntime, installed=lambda: (True, ""), resources=lambda: (True, ""))
    with _client(app, token) as client:  # runs the startup hook: nothing loads
        assert client.get("/health").json()["status"] == "unloaded"
        assert asked == []  # asking CUDA for free memory would create the context the service is meant not to hold
        assert _prepare(client).get("code") in {"warming", None}  # a call's prepare starts the load
        for _ in range(200):
            if app.state.host.status == "ready":
                break
            time.sleep(0.01)
        assert _prepare(client)["ok"] is True
        assert client.get("/health").json()["gpu"] == {"vram_free_bytes": 8 * 1024**3}


def test_an_unloaded_idle_model_asks_its_launcher_to_start_the_service_again_light(token: str) -> None:
    from app.runtime.process_control import IDLE_EXIT_CODE

    app = _ready_app(FakeRuntime(), idle_unload_seconds=0.0)
    exits: list[int] = []
    app.state.request_exit = exits.append
    with _client(app, token):  # the housekeeping task runs once a second
        for _ in range(300):
            if exits:
                break
            time.sleep(0.01)
    assert exits == [IDLE_EXIT_CODE] and app.state.host.status == "unloaded"


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
