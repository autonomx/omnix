"""Measure real PostgreSQL assembly and reads in a disposable baseline database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


async def measure(samples):
    import httpx
    from app.production import create_production_app, production_readiness
    from app.persistence.database import close_default_database

    started = time.perf_counter()
    gateway = create_production_app()
    composition_ms = (time.perf_counter() - started) * 1000
    # Exercise the read-only readiness probe at the PostgreSQL boundary.
    # Startup hooks are intentionally omitted: this benchmark never starts
    # trading monitors, external providers, speech or image execution workers.
    metrics = {}
    try:
        ready = production_readiness()
        assert ready["ready"], ready
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway), base_url="http://benchmark"
        ) as client:
            for route in ["/health", "/api/jobs?limit=100", "/api/assets"]:
                values = []
                for _ in range(samples):
                    started = time.perf_counter()
                    response = await client.get(route)
                    if response.status_code != 200:
                        raise RuntimeError(f"{route}: HTTP {response.status_code}")
                    values.append((time.perf_counter() - started) * 1000)
                values.sort()
                metrics[route] = {
                    "p50_ms": statistics.median(values),
                    "p95_ms": values[min(len(values) - 1, int(len(values) * 0.95))],
                    "max_ms": max(values),
                }
        return {
            "schema_version": 1,
            "mode": "disposable_postgresql_no_background_hooks",
            "python": platform.python_version(),
            "samples": samples,
            "production_composition_including_migrations_ms": composition_ms,
            "readiness": ready,
            "routes": metrics,
        }
    finally:
        close_default_database()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument(
        "--local-disposable",
        action="store_true",
        help="use the disposable Docker baseline container on port 16432",
    )
    args = parser.parse_args()
    url = os.environ.get("OMNIX_BENCHMARK_DATABASE_URL", "")
    if args.local_disposable:
        url = "postgresql://omnix_baseline:baseline_disposable@127.0.0.1:16432/omnix_refactor_baseline"
    if urlparse(url).path != "/omnix_refactor_baseline" or args.samples < 1:
        parser.error(
            "requires OMNIX_BENCHMARK_DATABASE_URL pointing to omnix_refactor_baseline and positive samples"
        )
    os.environ["OMNIX_DATABASE_URL"] = url
    os.environ["OMNIX_PERSISTENCE_MODE"] = "postgresql"
    result = asyncio.run(measure(args.samples))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
