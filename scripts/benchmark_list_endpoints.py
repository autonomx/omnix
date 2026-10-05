"""Time the list endpoints against a seeded disposable database (WP-7.6).

Seed first with ``scripts/seed_benchmark_data.py``. The production app is
composed against ``OMNIX_DATABASE_URL`` (no background workers start) and
each route is requested ``--samples`` times; the report gives p50/p95/max per
route and flags routes whose p95 exceeds the budget.

    OMNIX_DATABASE_URL=postgresql://omnix:omnix@127.0.0.1:55433/omnix_bench \\
        python scripts/benchmark_list_endpoints.py --output docs/measurements/query-pass.json
"""
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
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

BUDGET_P95_MS = 100.0


def _sample_ids(url: str) -> dict[str, str]:
    import psycopg

    with psycopg.connect(url) as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', false)")

        def one(sql: str) -> str:
            row = connection.execute(sql).fetchone()
            if row is None:
                raise SystemExit("seed the database first (scripts/seed_benchmark_data.py)")
            return str(row[0])

        return {
            "session_id": one("SELECT session_id FROM omnix_chat_messages GROUP BY session_id ORDER BY count(*) DESC LIMIT 1"),
            "run_id": one("SELECT run_id FROM omnix_agent_run_events GROUP BY run_id ORDER BY count(*) DESC LIMIT 1"),
            "strategy_id": one("SELECT strategy_id FROM omnix_trading_strategy_events GROUP BY strategy_id ORDER BY count(*) DESC LIMIT 1"),
        }


async def measure(samples: int) -> dict:
    import httpx

    from app.composition.production import create_production_app

    ids = _sample_ids(os.environ["OMNIX_DATABASE_URL"])
    routes = [
        "/api/assets?limit=50",
        "/api/jobs?limit=100",
        "/api/jobs?limit=100&status=completed",
        "/api/chat/sessions?limit=100",
        f"/api/chat/sessions/{ids['session_id']}",
        f"/api/agent-runs/{ids['run_id']}/events?limit=500",
        "/api/trading/strategies",
        f"/api/trading/strategies/{ids['strategy_id']}/events",
    ]
    gateway = create_production_app()
    results = {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway, raise_app_exceptions=False),
        base_url="http://127.0.0.1",
        headers={"X-Omnix-Client": "benchmark"},
        timeout=120,
    ) as client:
        for route in routes:
            first = await client.get(route)  # warm route state and caches
            if first.status_code != 200:
                results[route] = {"status": first.status_code, "error": first.text[:300]}
                continue
            values = []
            for _ in range(samples):
                started = time.perf_counter()
                response = await client.get(route)
                values.append((time.perf_counter() - started) * 1000)
                if response.status_code != 200:
                    raise RuntimeError(f"{route}: HTTP {response.status_code}")
            values.sort()
            p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
            results[route] = {
                "p50_ms": round(statistics.median(values), 2),
                "p95_ms": round(p95, 2),
                "max_ms": round(max(values), 2),
                "within_budget": p95 < BUDGET_P95_MS,
                "response_bytes": len(first.content),
            }
    return {
        "schema_version": 1,
        "measurement": "list endpoint latency at benchmark volumes (WP-7.6)",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "database": (urlparse(os.environ["OMNIX_DATABASE_URL"]).path or "").lstrip("/"),
        "samples": samples,
        "budget_p95_ms": BUDGET_P95_MS,
        "routes": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    name = (urlparse(os.environ.get("OMNIX_DATABASE_URL", "")).path or "").lstrip("/")
    if not any(marker in name for marker in ("test", "bench")):
        raise SystemExit("OMNIX_DATABASE_URL must name a disposable database (containing 'test' or 'bench')")
    result = asyncio.run(measure(args.samples))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["routes"], indent=2))


if __name__ == "__main__":
    main()
