"""Real-model smoke test of the desktop model services on their runtime packs (desktop roadmap DT-0.1, gate item 5).

    python scripts/desktop_smoke.py --packs DIR --database-url URL [--python PYTHON] [--service tts|stt|image|all]

Starts each service exactly as the desktop supervisor does (``python -S -m app.desktop.service_boot <service>`` with
the §4.2 environment, on the packs' shared Torch layer and its overlay), one at a time, and checks it does its job:

- tts: speaks a sentence (a WAV comes back);
- stt: the live websocket returns partial transcripts, an end of utterance (Parakeet EOU) and a final transcript of
  that WAV, and batch /transcribe agrees;
- image: loads FLUX.2 klein and generates one picture.

Each service is stopped before the next starts, and memory headroom is checked first (a load past it can freeze a
Windows PC). ``--database-url`` is a scratch database for the device permits; never the live one.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.desktop.env import LaunchConfig, service_environment  # noqa: E402
from app.desktop.services import plans, stop_gracefully  # noqa: E402
from app.models import catalog as model_catalog  # noqa: E402
from app.models.packs import ModelStore, RuntimeStore  # noqa: E402
from app.providers.host_memory import available_commit_bytes  # noqa: E402

PORTS = {"stt": 47931, "tts": 47932, "image": 47933}
SENTENCE = "Hello from the Omnix desktop app. The shared Torch layer works for every service."
CLIENT = {"X-Omnix-Client": "desktop-smoke"}


def _start(service: str, config: LaunchConfig, python: str, token: str, database_url: str, log: Path) -> subprocess.Popen:
    catalog = model_catalog.load()
    runtimes = RuntimeStore(config.packs, catalog)
    models = ModelStore(config.models_cache, catalog)
    plan = plans(config, catalog, runtimes, models).get(service)
    if plan is None:
        raise SystemExit(f"{service}: no installed bundle needs it in {config.packs}")
    available = available_commit_bytes()
    if available is not None and available < plan.needed_bytes:
        raise SystemExit(f"{service}: only {available / 2**30:.1f} GB of commit left, {plan.needed_bytes / 2**30:.1f} GB needed")
    inherited = {name: os.environ[name] for name in ("SystemRoot", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "PATH")
                 if os.environ.get(name)}
    inherited["OMNIXDESKTOP_DB_APP_PASSWORD"] = "unused"
    env = service_environment(config, service, service_token=token, site_dirs=plan.site_dirs, model_dir=plan.model_dir,
                              inherited=inherited)
    env["OMNIX_DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(ROOT / "src")  # a development interpreter; the bundled one has its ._pth
    print(f"{service}: starting on port {config.port(service)} ({plan.runtime}, {[p.parent.name for p in plan.site_dirs]})")
    group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0
    return subprocess.Popen([python, "-S", "-m", "app.desktop.service_boot", plan.entry], env=env,
                            stdout=log.open("ab"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            cwd=str(config.data_dir), creationflags=group)


def _wait_healthy(port: int, process: subprocess.Popen, timeout: float = 600.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the service exited with {process.returncode}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("the service did not become healthy")


def _sample() -> dict:
    """GPU memory in use and commit left now (DT-0.4 measures a service as the difference with it loaded)."""
    used = None
    try:
        output = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=10).stdout
        used = int(output.split()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    commit = available_commit_bytes()
    return {"vram_used_mb": used, "commit_available_mb": None if commit is None else commit // 2**20}


def _stop(process: subprocess.Popen) -> None:
    # As the supervisor does: a graceful stop releases the service's GPU model ownership for the next one.
    stop_gracefully(process, timeout=30)


def smoke_tts(port: int, token: str, out: Path) -> Path:
    import httpx

    headers = {**CLIENT, "X-Omnix-Service-Token": token, "Accept": "audio/wav"}
    started = time.monotonic()
    response = httpx.post(f"http://127.0.0.1:{port}/api/tts/generate_audio", headers=headers,
                          json={"text": SENTENCE}, timeout=600)
    response.raise_for_status()
    if not response.content.startswith(b"RIFF"):
        raise RuntimeError(f"tts: not a WAV ({response.headers.get('content-type')})")
    wav = out / "smoke-tts.wav"
    wav.write_bytes(response.content)
    with wave.open(str(wav)) as reader:
        seconds = reader.getnframes() / reader.getframerate()
    print(f"tts: ok, {seconds:.1f} s of speech in {time.monotonic() - started:.1f} s -> {wav}")
    return wav


def _pcm16_16k(wav: Path) -> bytes:
    import numpy as np

    with wave.open(str(wav)) as reader:
        rate, channels, width = reader.getframerate(), reader.getnchannels(), reader.getsampwidth()
        frames = reader.readframes(reader.getnframes())
    if width != 2:
        raise RuntimeError("expected 16-bit PCM")
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    target = int(len(samples) * 16000 / rate)
    resampled = np.interp(np.linspace(0, len(samples) - 1, target), np.arange(len(samples)), samples)
    silence = np.zeros(16000 * 2, dtype=np.float32)  # two seconds of silence, for the end of utterance
    return np.concatenate([resampled, silence]).clip(-32768, 32767).astype(np.int16).tobytes()


async def _live(port: int, token: str, pcm: bytes) -> dict:
    import websockets

    seen: dict = {"partial": [], "endpoint": False, "final": None, "types": set()}
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws/transcribe",
                                  additional_headers={"X-Omnix-Service-Token": token}, max_size=None,
                                  open_timeout=120) as socket:
        async def reader() -> None:
            async for raw in socket:
                message = json.loads(raw)
                kind = message.get("type")
                seen["types"].add(kind)
                if kind == "partial":
                    seen["partial"].append(message.get("text", ""))
                elif kind == "endpoint_candidate":
                    seen["endpoint"] = True
                elif kind == "result_available":
                    seen["final"] = message
                    return

        task = asyncio.create_task(reader())
        await socket.send(json.dumps({"type": "hello", "sessionId": "desktop-smoke"}))
        chunk = 16000 * 2 // 5  # 200 ms of 16 kHz PCM16
        for offset in range(0, len(pcm), chunk):
            await socket.send(json.dumps({"type": "audio", "segmentId": "smoke-1", "sequence": 1, "sampleRate": 16000,
                                          "sampleStart": offset // 2,
                                          "data": base64.b64encode(pcm[offset:offset + chunk]).decode()}))
            await asyncio.sleep(0.2)
        await socket.send(json.dumps({"type": "finalize", "segmentId": "smoke-1", "sequence": 1,
                                      "endSample": len(pcm) // 2}))
        await asyncio.wait_for(task, timeout=120)
    return seen


def smoke_stt(port: int, token: str, wav: Path) -> None:
    import httpx

    pcm = _pcm16_16k(wav)
    started = time.monotonic()
    seen = asyncio.run(_live(port, token, pcm))
    final = seen["final"] or {}
    text = str(final.get("text") or final.get("transcript") or "")
    print(f"stt live: {len(seen['partial'])} partials, end of utterance {'yes' if seen['endpoint'] else 'NO'}, "
          f"final {text!r} in {time.monotonic() - started:.1f} s; messages {sorted(seen['types'])}")
    if not seen["endpoint"] or not text:
        raise RuntimeError("stt: live transcription did not return an end of utterance and a final transcript")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(pcm)
    response = httpx.post(f"http://127.0.0.1:{port}/transcribe", headers={**CLIENT, "X-Omnix-Service-Token": token},
                          files={"file": ("smoke.wav", buffer.getvalue(), "audio/wav")}, timeout=300)
    response.raise_for_status()
    print(f"stt batch: {response.json().get('text')!r}")


def smoke_image(port: int, token: str, out: Path) -> None:
    import httpx

    headers = {**CLIENT, "X-Omnix-Service-Token": token}
    started = time.monotonic()
    loaded = httpx.post(f"http://127.0.0.1:{port}/provider/load", headers=headers, json={"provider": "flux_klein"},
                        timeout=900)
    print(f"image load: {loaded.status_code} in {time.monotonic() - started:.0f} s")
    loaded.raise_for_status()
    started = time.monotonic()
    response = httpx.post(f"http://127.0.0.1:{port}/generate", headers=headers, timeout=900, json={
        "provider": "flux_klein", "prompt": "a small red cube on a wooden table, studio light", "width": 512,
        "height": 512, "steps": 4, "seed": 7})
    response.raise_for_status()
    body = response.json()
    if body.get("ok") and body.get("local_path") and Path(body["local_path"]).is_file():
        written = Path(body["local_path"])
        print(f"image: ok, {body.get('width')}x{body.get('height')} ({written.stat().st_size} bytes) in "
              f"{time.monotonic() - started:.1f} s -> {written}")
        return
    encoded = next((body[key] for key in ("image_base64", "image", "b64_json") if isinstance(body.get(key), str)), None)
    if encoded is None and isinstance(body.get("images"), list) and body["images"]:
        first = body["images"][0]
        encoded = first if isinstance(first, str) else first.get("b64_json") or first.get("image_base64")
    if not encoded:
        raise RuntimeError(f"image: no picture in the response (keys {sorted(body)})")
    picture = out / "smoke-image.png"
    picture.write_bytes(base64.b64decode(encoded.split(",", 1)[-1]))
    print(f"image: ok, {picture.stat().st_size} bytes in {time.monotonic() - started:.1f} s -> {picture}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--packs", required=True, type=Path)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--service", choices=["tts", "stt", "image", "all"], default="all")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--measure", action="store_true", help="record VRAM and commit each service uses (DT-0.4)")
    args = parser.parse_args(argv)
    if ":5432/" in args.database_url:
        print("refusing port 5432: use a scratch database, never the live one", file=sys.stderr)
        return 2
    out = args.out or Path(tempfile.mkdtemp(prefix="omnix-desktop-smoke-"))
    out.mkdir(parents=True, exist_ok=True)
    config = LaunchConfig(install_root=ROOT, data_dir=out / "data", http_port=47930, pg_port=1, metrics_port=1,
                          notify_port=1, service_ports=PORTS, packs_dir=args.packs)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    services = ["tts", "stt", "image"] if args.service == "all" else [args.service]
    wav = out / "smoke-tts.wav"
    failed = False
    measured: dict[str, dict] = {}
    for service in services:
        log = out / f"{service}.log"
        before = _sample()
        process = _start(service, config, args.python, token, args.database_url, log)
        try:
            _wait_healthy(PORTS[service], process)
            if service == "tts":
                wav = smoke_tts(PORTS[service], token, out)
            elif service == "stt":
                if not wav.is_file():
                    raise RuntimeError("stt needs the tts WAV: run tts first")
                smoke_stt(PORTS[service], token, wav)
            else:
                smoke_image(PORTS[service], token, out)
            if args.measure:
                after = _sample()
                measured[service] = {
                    "vram_mb": None if None in (before["vram_used_mb"], after["vram_used_mb"])
                    else after["vram_used_mb"] - before["vram_used_mb"],
                    "commit_mb": None if None in (before["commit_available_mb"], after["commit_available_mb"])
                    else before["commit_available_mb"] - after["commit_available_mb"],
                }
                print(f"{service} uses: {measured[service]}")
        except Exception as exc:  # report and go on to the next service
            failed = True
            print(f"{service}: FAILED: {exc}; see {log}")
        finally:
            _stop(process)
    if args.measure:
        (out / "measurements.json").write_text(json.dumps(measured, indent=1) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
