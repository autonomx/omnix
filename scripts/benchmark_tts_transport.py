"""Measure TTS first-audio latency and memory over a long synthesis (WP-7.3).

Drives a running TTS service through the gateway's own client
(``QwenHttpGatewayProvider``), so the numbers include the PCM16 streaming
transport (``/api/tts/live-call/stream``) and the WAV whole-utterance path
(``/api/tts/generate_audio`` with ``Accept: audio/wav``):

- first audio: time from the request to the first PCM chunk the gateway
  client yields, for short utterances (after one warm-up);
- whole utterance: time to the WAV bytes for the same text;
- long synthesis: paragraphs streamed back to back until ``--minutes`` of audio
  have been produced, sampling the service's and this client's resident memory
  and the GPU's memory in use (``nvidia-smi``) once a second.

Run it against a TTS service you started for the measurement, with
``OMNIX_SERVICE_TOKEN`` set to that service's token:

    OMNIX_SERVICE_TOKEN=... python scripts/benchmark_tts_transport.py --url http://127.0.0.1:5111 \\
        --service-pid 1234 --output docs/measurements/tts-transport.json
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SHORT = "The lantern swung once in the wind, and the harbor went quiet."
PARAGRAPH = (
    "The road to the harbor ran between low stone walls and fields that had not been ploughed in years. "
    "At the top of the last hill the traveler stopped, set down her pack and looked at the town below: the "
    "slate roofs, the smoke from a dozen chimneys, the masts of the fishing boats rocking at the quay. "
    "Somewhere a bell was ringing for the evening, slow and patient, and the gulls answered it."
)


def _rss_mb(pid: int) -> float:
    import psutil

    return psutil.Process(pid).memory_info().rss / 2**20


def _gpu_mb() -> float | None:
    """Device memory in use. Per-process figures are not available under Windows (WDDM), so this
    is the whole GPU; the long synthesis reports its growth from the start."""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    values = [float(line) for line in output.split() if line.strip()]
    return values[0] if values else None


def _percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {"p50_ms": round(statistics.median(ordered), 1),
            "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 1),
            "max_ms": round(max(ordered), 1)}


def first_audio(provider, samples: int) -> dict:
    first, total, audio_seconds = [], [], []
    for index in range(samples + 1):
        started = time.perf_counter()
        first_ms = None
        samples_out = 0
        rate = 24_000
        for chunk, rate, _timing in provider.generate_audio_stream(SHORT, speaker="default", language="en"):
            if first_ms is None:
                first_ms = (time.perf_counter() - started) * 1000
            samples_out += len(chunk)
        if index == 0:
            continue  # warm-up
        first.append(first_ms or 0.0)
        total.append((time.perf_counter() - started) * 1000)
        audio_seconds.append(samples_out / rate)
    return {"stream_first_audio": _percentiles(first), "stream_total": _percentiles(total),
            "audio_seconds_per_utterance": round(statistics.median(audio_seconds), 2)}


def whole_utterance(provider, samples: int) -> dict:
    values = []
    for index in range(samples + 1):
        started = time.perf_counter()
        result = provider.generate_audio(SHORT, speaker="default", language="en")
        if not result.get("success"):
            raise RuntimeError("the service returned no audio")
        if index:
            values.append((time.perf_counter() - started) * 1000)
    return _percentiles(values)


def long_synthesis(provider, service_pid: int, minutes: float) -> dict:
    import os

    target_seconds = minutes * 60
    produced = 0.0
    peaks = {"service_rss_mb": 0.0, "client_rss_mb": 0.0, "gpu_used_mb": 0.0}
    start_memory = {"service_rss_mb": _rss_mb(service_pid), "client_rss_mb": _rss_mb(os.getpid()),
                    "gpu_used_mb": _gpu_mb()}
    done = threading.Event()

    def sample() -> None:
        while not done.is_set():
            peaks["service_rss_mb"] = max(peaks["service_rss_mb"], _rss_mb(service_pid))
            peaks["client_rss_mb"] = max(peaks["client_rss_mb"], _rss_mb(os.getpid()))
            gpu = _gpu_mb()
            if gpu is not None:
                peaks["gpu_used_mb"] = max(peaks["gpu_used_mb"], gpu)
            done.wait(1.0)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.perf_counter()
    requests = 0
    try:
        while produced < target_seconds:
            for chunk, rate, _timing in provider.generate_audio_stream(PARAGRAPH, speaker="default", language="en"):
                produced += len(chunk) / rate  # consumed and dropped, as a player would
            requests += 1
    finally:
        done.set()
        sampler.join()
    wall = time.perf_counter() - started
    return {
        "audio_seconds": round(produced, 1),
        "requests": requests,
        "wall_seconds": round(wall, 1),
        "real_time_factor": round(wall / produced, 3) if produced else None,
        "memory_at_start": {key: (round(value, 1) if value is not None else None) for key, value in start_memory.items()},
        "memory_peak": {key: round(value, 1) for key, value in peaks.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--service-pid", type=int, required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from app.providers.qwen_http_gateway import QwenHttpGatewayProvider

    provider = QwenHttpGatewayProvider(args.url)
    health = provider._health()
    if not health.get("ok"):
        raise SystemExit(f"the TTS service is not ready: {health}")
    result = {
        "schema_version": 1,
        "measurement": "TTS first-audio latency and long-synthesis memory (WP-7.3)",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "service": health.get("details", {}),
        "transport": "http_streaming_pcm16 (live-call stream), audio/wav (whole utterance)",
        "short_text_chars": len(SHORT),
        "samples": args.samples,
        **first_audio(provider, args.samples),
        "whole_utterance_wav": whole_utterance(provider, args.samples),
        "long_synthesis": long_synthesis(provider, args.service_pid, args.minutes),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
