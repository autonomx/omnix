"""Repeatable, provider-free gateway event-loop benchmark; never opens PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


async def measure(samples: int, delay_ms: float) -> dict:
    started = time.perf_counter()
    from app.gateway.main import _live_job_event_stream, create_gateway_app
    import httpx

    import_ms = (time.perf_counter() - started) * 1000

    class SlowStore:
        def list_events(self, **kwargs):
            time.sleep(delay_ms / 1000)
            return []

        def get_job(self, job_id):
            time.sleep(delay_ms / 1000)
            return None

    store = SlowStore()
    started = time.perf_counter()
    gateway = create_gateway_app(job_store_factory=lambda: store)
    composition_ms = (time.perf_counter() - started) * 1000
    transport = httpx.ASGITransport(app=gateway)
    health_ms, stream_lag_ms = [], []
    async with httpx.AsyncClient(
        transport=transport, base_url="http://benchmark"
    ) as client:
        for _ in range(samples):
            busy = asyncio.create_task(client.get("/api/jobs/missing"))
            started = time.perf_counter()
            await asyncio.sleep(0.001)
            response = await client.get("/health")
            assert response.status_code == 200
            health_ms.append((time.perf_counter() - started) * 1000)
            assert (await busy).status_code == 404
            stream = _live_job_event_stream(store)
            await anext(stream)
            poll = asyncio.create_task(anext(stream))
            started = time.perf_counter()
            await asyncio.sleep(0.001)
            stream_lag_ms.append((time.perf_counter() - started) * 1000)
            await poll
            await stream.aclose()

    def summary(values):
        ordered = sorted(values)
        return {
            "p50_ms": statistics.median(ordered),
            "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
            "p99_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))],
            "max_ms": max(ordered),
        }

    return {
        "schema_version": 1,
        "mode": "synthetic_provider_free_no_lifespan",
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "database_configured": bool(os.environ.get("OMNIX_DATABASE_URL")),
        "samples": samples,
        "error_count": 0,
        "active_requests_at_end": gateway.state.runtime_metrics.snapshot()['active_requests'],
        "recovery_duration_ms": None,
        "simulated_store_delay_ms": delay_ms,
        "gateway_import_ms": import_ms,
        "gateway_composition_ms": composition_ms,
        "health_during_job_read": summary(health_ms),
        "event_loop_lag_during_sse_poll": summary(stream_lag_ms),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--delay-ms", type=float, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1 or args.delay_ms < 0:
        parser.error("samples must be positive and delay must be nonnegative")
    result = asyncio.run(measure(args.samples, args.delay_ms))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
