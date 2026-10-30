"""The live portrait end to end: the gateway's TTS and avatar websockets against the real portrait service.

Opt-in (it starts the portrait service on the GPU and loads FLOAT, about a minute): set
``OMNIX_PORTRAIT_E2E_PYTHON`` to the ``omnix-portrait`` interpreter. ``OMNIX_PORTRAIT_E2E_AUDIO`` and
``OMNIX_PORTRAIT_E2E_PHOTO`` choose the clip and the photo; ``OMNIX_PORTRAIT_E2E_OUT`` keeps the measurements.
Only the TTS engine and the session's avatar pack are stand-ins: a provider that speaks a recorded clip as two
phrases at three times real time, and a portrait pack whose image is the photo.
"""
from __future__ import annotations

import io
import json
import os
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
PYTHON = os.environ.get("OMNIX_PORTRAIT_E2E_PYTHON", "")
AUDIO = Path(os.environ.get("OMNIX_PORTRAIT_E2E_AUDIO", ROOT / "resources" / "voice_clones" / "Maya.wav"))
PHOTO = Path(os.environ.get("OMNIX_PORTRAIT_E2E_PHOTO",
                            ROOT / "resources" / "cache" / "portrait-spike" / "float-upstream" / "assets" / "sam_altman.webp"))
RATE = 24_000
PACE = 3.0

pytestmark = pytest.mark.skipif(not PYTHON, reason="set OMNIX_PORTRAIT_E2E_PYTHON to run the live portrait end to end")


def _clip_24k() -> np.ndarray:
    import soundfile

    audio, rate = soundfile.read(str(AUDIO), dtype="float32", always_2d=True)
    mono = audio[:, 0]
    positions = np.arange(int(len(mono) * RATE / rate)) * (rate / RATE)
    return np.interp(positions, np.arange(len(mono)), mono).astype(np.float32)


class ClipTtsProvider:
    """Speaks a recorded clip: each phrase text names which half to stream, in 80 ms chunks."""

    provider_name = "clip"
    tts_capabilities = {"provider": "clip", "supports_streaming": True, "supports_concurrent_generation": False,
                        "supports_emotion": False, "supports_speaking_rate": False, "supports_word_emphasis": False,
                        "supports_ssml": False, "supports_word_timestamps": False}

    def __init__(self, halves: list[np.ndarray]) -> None:
        self.halves = halves

    def generate_audio_stream(self, *, text: str, **_kwargs: Any):
        audio = self.halves[int(text.split()[-1])]
        chunk = RATE * 80 // 1000
        for start in range(0, len(audio), chunk):
            time.sleep(chunk / RATE / PACE)
            yield audio[start:start + chunk], RATE, {}


@pytest.fixture(scope="module")
def portrait_service():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = {**os.environ, "OMNIX_SERVICE_TOKEN": token, "OMNIX_BIND_HOST": "127.0.0.1",
           "OMNIX_PORTRAIT_PORT": str(port), "PYTHONPATH": str(ROOT / "src")}
    out = os.environ.get("OMNIX_PORTRAIT_E2E_OUT")
    log = open(Path(out).with_suffix(".service.log"), "w", encoding="utf-8") if out else subprocess.DEVNULL  # noqa: SIM115
    process = subprocess.Popen([PYTHON, "-m", "services.portrait.portrait_server"], cwd=ROOT, env=env,
                               stdout=log, stderr=subprocess.STDOUT)
    import httpx

    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 300
        status = ""
        while time.monotonic() < deadline and process.poll() is None:
            try:
                status = httpx.get(f"{url}/health", timeout=2).json()["status"]
            except httpx.HTTPError:
                status = ""
            if status in {"ready", "missing", "short", "failed"}:
                break
            time.sleep(1)
        assert status == "ready", f"the portrait service did not load ({status or 'no answer'})"
        yield SimpleNamespace(url=url, token=token)
    finally:
        process.terminate()
        process.wait(timeout=30)


def test_a_call_streams_its_portrait_end_to_end(monkeypatch, portrait_service) -> None:
    from app.conversation.portrait_stream_contract import unpack
    from app.platform.characters.avatar_models import CharacterAvatarPack
    from app.platform.live_voice.transport import avatar_websocket
    from PIL import Image
    from tests.app.test_gateway_tts_live_call_websocket import _configure_gateway, _request

    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", portrait_service.token)
    monkeypatch.setenv("OMNIX_PORTRAIT_URL", portrait_service.url)
    pack = CharacterAvatarPack(character_id="e2e", renderer="portrait", base_asset_id="image:e2e",
                               created_at="2026-10-30T00:00:00+00:00", updated_at="2026-10-30T00:00:00+00:00")
    photo = PHOTO.read_bytes()
    monkeypatch.setattr(avatar_websocket, "_load_session", lambda factory, session_id: SimpleNamespace(id=session_id))
    monkeypatch.setattr(avatar_websocket, "resolve_live_call_runtime", lambda session: SimpleNamespace(avatar_pack=pack))
    monkeypatch.setattr(avatar_websocket, "default_character_avatar_service",
                        lambda: SimpleNamespace(portrait_image=lambda pack, max_bytes: photo))
    clip = _clip_24k()
    halves = [clip[: len(clip) // 2], clip[len(clip) // 2:]]
    client, _logs = _configure_gateway(monkeypatch, ClipTtsProvider(halves))

    frames: list[tuple[dict, bytes, float]] = []
    status: dict[str, Any] = {}
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        hello = tts.receive_json()
        with client.websocket_connect(
                f"/api/tts/live-call/avatar-websocket?token={hello['avatar_token']}&session_id=e2e") as avatar:
            started = time.perf_counter()
            status["avatar"] = avatar.receive_json()
            status["avatar_ready_ms"] = round((time.perf_counter() - started) * 1000)
            assert status["avatar"]["type"] == "ready", status["avatar"]
            stop = threading.Event()

            def read_frames() -> None:
                while not stop.is_set():
                    try:
                        message = avatar.receive_bytes()
                    except Exception:  # noqa: BLE001 - the socket closed
                        return
                    header, jpeg = unpack(message)
                    frames.append((header, jpeg, time.perf_counter()))

            reader = threading.Thread(target=read_frames, daemon=True)
            reader.start()
            outputs: dict[str, dict[str, Any]] = {}
            for epoch in (1, 2):  # two replies (turns) on one call: the second shows the warm path
                output_id = f"turn-{epoch}"  # the portrait names a reply after its turn
                sent = 0
                for index in range(2):
                    tts.send_json({**_request(f"half {index}", index), "output_id": f"conversation-g{epoch}-p{index}",
                                   "generation_epoch": epoch, "segment_id": f"{output_id}-seg-{index}"})
                    assert tts.receive_json()["type"] == "start"
                    while True:
                        message = tts.receive()
                        if message.get("bytes") is not None:
                            outputs.setdefault(output_id, {"first_pcm_at": time.perf_counter()})
                            sent += len(message["bytes"]) // 2
                            continue
                        if json.loads(message["text"])["type"] == "done":
                            break
                tts.send_json({"type": "output_end", "output_id": f"conversation-g{epoch}-p1", "generation_epoch": epoch})
                # Frames cover the audio the browser got (16 kHz, 640 samples a frame, the last one partial).
                outputs[output_id]["expected"] = -(-(sent * 16_000 // RATE) // 640)
                deadline = time.monotonic() + 30
                while (sum(1 for h, _j, _a in frames if h["output_id"] == output_id) < outputs[output_id]["expected"]
                       and time.monotonic() < deadline):
                    time.sleep(0.05)
                time.sleep(1.0)  # a pause between replies, as in a call
            stop.set()

    results: dict[str, Any] = {"audio_seconds_per_reply": round(len(clip) / RATE, 2),
                               "avatar_ready_ms": status["avatar_ready_ms"], "replies": {}}
    for output_id, output in outputs.items():
        mine = [(h, j, at) for h, j, at in frames if h["output_id"] == output_id]
        segments = [h["segment_id"] for h, _j, _a in mine]
        results["replies"][output_id] = {
            "frames": len(mine), "expected": output["expected"],
            "segments_in_order": segments == sorted(segments),
            "offsets_rising_per_segment": all(
                [h["offset"] for h, _j, _a in mine if h["segment_id"] == segment]
                == sorted(h["offset"] for h, _j, _a in mine if h["segment_id"] == segment) for segment in set(segments)),
            "decodable_512": sum(1 for _h, jpeg, _a in mine if Image.open(io.BytesIO(jpeg)).size == (512, 512)),
            "first_frame_after_first_pcm_ms": round((mine[0][2] - output["first_pcm_at"]) * 1000) if mine else None,
        }
    out = os.environ.get("OMNIX_PORTRAIT_E2E_OUT")
    if out:
        Path(out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    for reply in results["replies"].values():
        # Each phrase's last frame may be partial, so a reply can have one frame more per phrase.
        assert reply["expected"] <= reply["frames"] <= reply["expected"] + 2
        assert reply["segments_in_order"] and reply["offsets_rising_per_segment"]
        assert reply["decodable_512"] == reply["frames"]
