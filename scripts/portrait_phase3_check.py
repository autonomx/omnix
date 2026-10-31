"""Live portrait Phases 3-4 on the real model: the idle loop, quality levels, speculative frames and the preview.

Starts the portrait service from its own environment (as ``portrait_service_smoke.py`` does), prepares a photo
and checks, against FLOAT itself:

- the idle loop that follows ``ready``: its length, frame period, size, how long it took, and its seam (the
  pixel change from its last frame back to its first, against the median change between neighbouring frames);
- a reply at the opening level (L0): every frame, 512 px, in order;
- a reply after ``quality`` L3: every other frame, 384 px;
- a reply bound from speculation: the speculative frames go out at the bind, the rest after the prefix, every
  frame once and in order, and how long after the bind the first frame came;
- ``/portrait/preview`` for 4 s of the clip: the frame count and how long it took.

Refuses to start while the machine is busy. Writes ``portrait-phase3-check.json`` to ``--out``.

    .venv/dev-clean/Scripts/python.exe scripts/portrait_phase3_check.py --python <omnix-portrait python> \
        --photo <photo> --audio a.wav --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import secrets
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import portrait_spike as spike  # noqa: E402
from portrait_service_smoke import free_port  # noqa: E402


def _pixels(jpeg: bytes):
    import numpy as np
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"), dtype=np.float32)


def _size(jpeg: bytes) -> tuple[int, int]:
    from PIL import Image

    return Image.open(io.BytesIO(jpeg)).size


def idle_report(frames: list[tuple[dict, bytes]], seconds: float) -> dict:
    ordered = [jpeg for _header, jpeg in sorted(frames, key=lambda item: item[0]["offset"])]
    pixels = [_pixels(jpeg) for jpeg in ordered]
    steps = [float(abs(pixels[index + 1] - pixels[index]).mean()) for index in range(len(pixels) - 1)]
    seam = float(abs(pixels[0] - pixels[-1]).mean()) if len(pixels) > 1 else None
    header = frames[0][0] if frames else {}
    return {"frames": len(frames), "count": header.get("count"), "frame_ms": header.get("frame_ms"),
            "loop_seconds": round(len(frames) * (header.get("frame_ms") or 40) / 1000, 2),
            "size": list(_size(ordered[0])) if ordered else None, "arrived_after_ready_s": round(seconds, 2),
            "seam_mean_abs": round(seam, 2) if seam is not None else None,
            "neighbour_median_mean_abs": round(statistics.median(steps), 2) if steps else None}


async def check_stream(url: str, token: str, latent_key: str, pcm, rate: int, pace: float) -> dict:
    import websockets

    from app.conversation.portrait_stream_contract import pack, unpack

    headers = {"X-Omnix-Service-Token": token, "X-Omnix-Client": "phase3-check"}
    idle: list[tuple[dict, bytes]] = []
    speech: dict[str, list[tuple[dict, bytes, float]]] = {}
    block = rate // 25 * 2
    report: dict = {}
    async with websockets.connect(url, additional_headers=headers, max_size=None) as websocket:
        await websocket.send(json.dumps({"type": "open", "call_key": "check", "principal": "check", "session": "s",
                                         "latent_key": latent_key, "emotion": "neutral", "level": 0}))
        ready = json.loads(await websocket.recv())
        if ready.get("type") != "ready":
            return {"refused": ready}
        ready_at = time.perf_counter()
        idle_done = asyncio.Event()

        async def receive() -> None:
            while True:
                header, jpeg = unpack(await websocket.recv())
                if header["output_id"] == "idle":
                    idle.append((header, jpeg))
                    if len(idle) == header.get("count"):
                        report["idle_seconds"] = time.perf_counter() - ready_at
                        idle_done.set()
                else:
                    speech.setdefault(header["output_id"], []).append((header, jpeg, time.perf_counter()))

        receiver = asyncio.create_task(receive())

        async def speak(output: str, epoch: int, segment: str, audio, start: int = 0) -> float:
            await websocket.send(json.dumps({"type": "phrase_start", "output_id": output, "epoch": epoch,
                                             "segment_id": segment, "sample_rate": rate}))
            began = time.perf_counter()
            for offset in range(start, len(audio), block):
                await websocket.send(pack({"segment_id": segment, "offset": offset},
                                          audio[offset:offset + block].tobytes()))
                await asyncio.sleep(block / rate / pace)
            await websocket.send(json.dumps({"type": "phrase_done", "segment_id": segment}))
            await websocket.send(json.dumps({"type": "output_end", "output_id": output, "epoch": epoch}))
            return began

        async def settle(output: str, expected: int) -> None:
            deadline = time.perf_counter() + 30
            while len(speech.get(output, [])) < expected and time.perf_counter() < deadline:
                await asyncio.sleep(0.05)

        await asyncio.wait_for(idle_done.wait(), 60)
        expected = -(-len(pcm) * 16_000 // rate // 640)
        began = await speak("turn-1", 1, "seg-1", pcm)
        await settle("turn-1", expected)
        first = speech.get("turn-1", [])
        report["level0"] = {"frames": len(first), "expected": expected,
                            "in_order": [h["offset"] for h, _j, _t in first] == sorted(h["offset"] for h, _j, _t in first),
                            "sizes": sorted({_size(jpeg) for _h, jpeg, _t in first}),
                            "first_frame_ms": round((first[0][2] - began) * 1000) if first else None}

        await websocket.send(json.dumps({"type": "quality", "level": 3}))
        await speak("turn-2", 2, "seg-2", pcm)
        await settle("turn-2", (expected + 1) // 2)
        second = speech.get("turn-2", [])
        report["level3"] = {"frames": len(second), "expected": (expected + 1) // 2,
                            "sizes": sorted({_size(jpeg) for _h, jpeg, _t in second})}
        await websocket.send(json.dumps({"type": "quality", "level": 0}))

        # Speculation: the first 2 s arrive as speculative audio, then a reply replays it and goes on.
        prefix = min(len(pcm), rate * 2)
        await websocket.send(json.dumps({"type": "spec_start", "generation_id": "gen-1", "sample_rate": rate}))
        for offset in range(0, prefix, block):
            await websocket.send(pack({"segment_id": "spec:gen-1", "offset": offset},
                                      pcm[offset:min(prefix, offset + block)].tobytes()))
        await asyncio.sleep(1.0)  # the speculative output renders its first passes meanwhile
        await websocket.send(json.dumps({"type": "phrase_start", "output_id": "turn-3", "epoch": 3,
                                         "segment_id": "seg-3", "sample_rate": rate}))
        bound_at = time.perf_counter()
        await websocket.send(json.dumps({"type": "spec_bind", "generation_id": "gen-1", "output_id": "turn-3",
                                         "epoch": 3, "segment_id": "seg-3"}))
        await websocket.send(json.dumps({"type": "spec_prefix_end", "generation_id": "gen-1", "segment_id": "seg-3",
                                         "samples": prefix}))
        await asyncio.sleep(0.3)
        at_bind = len(speech.get("turn-3", []))
        for offset in range(prefix, len(pcm), block):
            await websocket.send(pack({"segment_id": "seg-3", "offset": offset}, pcm[offset:offset + block].tobytes()))
            await asyncio.sleep(block / rate / pace)
        await websocket.send(json.dumps({"type": "phrase_done", "segment_id": "seg-3"}))
        await websocket.send(json.dumps({"type": "output_end", "output_id": "turn-3", "epoch": 3}))
        await settle("turn-3", expected)
        third = speech.get("turn-3", [])
        offsets = [h["offset"] for h, _j, _t in third]
        report["speculation"] = {"frames": len(third), "expected": expected, "sent_within_300ms_of_bind": at_bind,
                                 "first_frame_after_bind_ms": round((third[0][2] - bound_at) * 1000) if third else None,
                                 "each_once_in_order": offsets == sorted(set(offsets))}
        receiver.cancel()
    report["idle"] = idle_report(idle, report.pop("idle_seconds", 0.0))
    return report


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
    headers = {"X-Omnix-Service-Token": token, "X-Omnix-Client": "phase3-check"}
    results: dict = {}
    try:
        started, status = time.perf_counter(), "starting"
        while time.perf_counter() - started < 300 and process.poll() is None:
            try:
                status = httpx.get(f"{base}/health", timeout=2).json()["status"]
                if status in {"ready", "missing", "short", "failed"}:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        results["ready_after_s"] = round(time.perf_counter() - started, 1)
        if status != "ready":
            results["status"] = status
            return 1
        photo = args.photo.read_bytes()
        prepared = httpx.post(f"{base}/portrait/prepare", headers=headers, timeout=60,
                              data={"tenant": "check", "image_sha256": hashlib.sha256(photo).hexdigest()},
                              files={"file": (args.photo.name, photo)}).json()
        audio, rate = soundfile.read(str(args.audio), dtype="int16")
        pcm = (audio if audio.ndim == 1 else audio[:, 0]).astype("<i2")
        results.update(asyncio.run(check_stream(f"ws://127.0.0.1:{port}/portrait/stream", token,
                                                prepared["latent_key"], pcm, rate, args.pace)))
        clip = pcm[: rate * 4]
        began = time.perf_counter()
        preview = httpx.post(f"{base}/portrait/preview", headers=headers, timeout=120,
                             data={"latent_key": prepared["latent_key"], "emotion": "happy", "sample_rate": str(rate)},
                             files={"file": ("clip.pcm", clip.tobytes())}).json()
        frames = preview.get("frames") or []
        results["preview"] = {"ok": preview.get("ok"), "frames": len(frames), "expected": -(-len(clip) * 25 // rate),
                              "ms": round((time.perf_counter() - began) * 1000),
                              "size": list(_size(base64.b64decode(frames[0]))) if frames else None}
        idle, level0, level3, spec = (results.get(key, {}) for key in ("idle", "level0", "level3", "speculation"))
        results["ok"] = bool(
            idle.get("frames") and idle.get("frames") == idle.get("count")
            and level0.get("frames") == level0.get("expected") and level0.get("sizes") == [(512, 512)]
            and level3.get("frames") == level3.get("expected") and level3.get("sizes") == [(384, 384)]
            and spec.get("frames") == spec.get("expected") and spec.get("each_once_in_order")
            and spec.get("sent_within_300ms_of_bind", 0) > 0
            and results["preview"]["frames"] == results["preview"]["expected"])
        return 0 if results["ok"] else 1
    finally:
        process.terminate()
        process.wait(timeout=30)
        log.close()
        (args.out / "portrait-phase3-check.json").write_text(json.dumps(results, indent=2, default=list),
                                                              encoding="utf-8")
        print(json.dumps(results, indent=2, default=list))


if __name__ == "__main__":
    raise SystemExit(main())
