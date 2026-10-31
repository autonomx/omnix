"""Live portrait Phase 1 smoke test: the service process itself, started from its own environment.

Starts ``services.portrait.portrait_server`` with the given interpreter on a free local port and a fresh
service token, waits for ``/health`` to report ``ready``, prepares a photo, streams a clip over the websocket
at the given pace (TTS runs faster than real time), and checks the frames: count, order, stamps, JPEG
validity, and the time from the first audio to the first frame. Stops the service at the end.
Refuses to start while the machine is busy (as the spike does).

    .venv/dev-clean/Scripts/python.exe scripts/portrait_service_smoke.py --python <omnix-portrait python> \
        --photo <photo> --audio a.wav --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import portrait_spike as spike  # noqa: E402


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def stream_clip(url: str, token: str, latent_key: str, pcm, rate: int, pace: float) -> dict:
    import websockets
    from PIL import Image

    from app.conversation.portrait_stream_contract import pack, unpack

    headers = {"X-Omnix-Service-Token": token, "X-Omnix-Client": "smoke"}
    frames: list[tuple[dict, bytes, float]] = []
    async with websockets.connect(url, additional_headers=headers, max_size=None) as websocket:
        await websocket.send(json.dumps({"type": "open", "call_key": "smoke", "principal": "smoke", "session": "s",
                                         "latent_key": latent_key, "emotion": "neutral"}))
        ready = json.loads(await websocket.recv())
        if ready.get("type") != "ready":
            return {"refused": ready}
        await websocket.send(json.dumps({"type": "phrase_start", "output_id": "out", "epoch": 1,
                                         "segment_id": "seg", "sample_rate": rate}))
        block = rate // 25 * 2  # 80 ms blocks, as TTS chunks arrive

        async def receive() -> None:
            while True:
                header, jpeg = unpack(await websocket.recv())
                frames.append((header, jpeg, time.perf_counter()))

        receiver = asyncio.create_task(receive())
        started = time.perf_counter()
        for offset in range(0, len(pcm), block):
            await websocket.send(pack({"segment_id": "seg", "offset": offset}, pcm[offset:offset + block].tobytes()))
            await asyncio.sleep(block / rate / pace)
        await websocket.send(json.dumps({"type": "phrase_done", "segment_id": "seg"}))
        await websocket.send(json.dumps({"type": "output_end", "output_id": "out", "epoch": 1}))
        expected = -(-len(pcm) * 16_000 // rate // 640)
        deadline = time.perf_counter() + 30
        while len(frames) < expected and time.perf_counter() < deadline:
            await asyncio.sleep(0.05)
        receiver.cancel()
    offsets = [header["offset"] for header, _jpeg, _at in frames]
    decodable = sum(1 for _header, jpeg, _at in frames if Image.open(io.BytesIO(jpeg)).size == (512, 512))
    return {"frames": len(frames), "expected": expected, "in_order": offsets == sorted(offsets),
            "decodable_512": decodable, "first_frame_after_first_audio_ms": round((frames[0][2] - started) * 1000)
            if frames else None, "stream_seconds": round(frames[-1][2] - started, 2) if frames else None,
            "audio_seconds": round(len(pcm) / rate, 2)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", type=Path, required=True, help="the omnix-portrait interpreter")
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pace", type=float, default=3.0, help="audio sent this many times faster than real time")
    parser.add_argument("--allow-busy", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import httpx
    import soundfile

    reasons = spike.busy_reasons(args.allow_busy)
    if reasons:
        print("Not starting; the machine looks busy:\n  " + "\n  ".join(reasons))
        return 2

    port, token = free_port(), secrets.token_urlsafe(32)
    env = {**os.environ, "OMNIX_SERVICE_TOKEN": token, "OMNIX_BIND_HOST": "127.0.0.1",
           "OMNIX_PORTRAIT_PORT": str(port), "PYTHONPATH": str(ROOT / "src")}
    log = (args.out / "service.log").open("w", encoding="utf-8")
    process = subprocess.Popen([str(args.python), "-m", "services.portrait.portrait_server"], cwd=ROOT, env=env,
                               stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    results: dict = {}
    try:
        started = time.perf_counter()
        status = "starting"
        while time.perf_counter() - started < 300:
            if process.poll() is not None:
                results["exited"] = process.returncode
                return 1
            try:
                health = httpx.get(f"{base}/health", timeout=2).json()
                status = health["status"]
                if status in {"ready", "missing", "short", "failed"}:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        results["ready_after_s"] = round(time.perf_counter() - started, 1)
        results["health"] = health if status != "starting" else None
        if status != "ready":
            return 1
        photo = args.photo.read_bytes()
        headers = {"X-Omnix-Service-Token": token, "X-Omnix-Client": "smoke"}
        began = time.perf_counter()
        prepared = httpx.post(f"{base}/portrait/prepare", headers=headers, timeout=60,
                              data={"tenant": "smoke", "image_sha256": hashlib.sha256(photo).hexdigest()},
                              files={"file": (args.photo.name, photo)}).json()
        results["prepare"] = {**prepared, "ms": round((time.perf_counter() - began) * 1000)}
        audio, rate = soundfile.read(str(args.audio), dtype="int16")
        pcm = (audio if audio.ndim == 1 else audio[:, 0]).astype("<i2")
        results["stream"] = asyncio.run(stream_clip(f"ws://127.0.0.1:{port}/portrait/stream", token,
                                                    prepared["latent_key"], pcm, rate, args.pace))
        results["health_after"] = httpx.get(f"{base}/health", timeout=2).json()
        stream = results["stream"]
        results["ok"] = bool(stream.get("frames") == stream.get("expected") == stream.get("decodable_512")
                             and stream.get("in_order"))
        return 0 if results["ok"] else 1
    finally:
        process.terminate()
        process.wait(timeout=30)
        log.close()
        out = args.out / "portrait-service-smoke.json"
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
