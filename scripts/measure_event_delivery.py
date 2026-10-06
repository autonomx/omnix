"""Idle database queries per second for /events subscribers (WP-5.4).

Compares the per-subscriber polling stream (before) with the shared
EventReader (after) on a disposable PostgreSQL database, for 1, 10 and 100
idle subscribers, after every stream has connected. Usage:

    OMNIX_TEST_DATABASE_URL=... python scripts/measure_event_delivery.py --seconds 10 --output out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SETTLE_SECONDS = 2.0


async def _before(store, subscribers: int, seconds: float) -> int:
    from app.composition.gateway.kernel_routes import live_event_stream

    calls = 0
    original = store.list_events

    def counted(**kwargs):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    store.list_events = counted

    async def consume() -> None:
        async for _ in live_event_stream.resilient_live_job_event_stream(store, after_id=store.latest_event_id()):
            pass

    tasks = [asyncio.create_task(consume()) for _ in range(subscribers)]
    await asyncio.sleep(SETTLE_SECONDS)
    settled = calls
    await asyncio.sleep(seconds)
    measured = calls - settled
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    store.list_events = original
    return measured


async def _after(database, tenant, subscribers: int, seconds: float) -> int:
    from app.events.event_reader import EventReader
    from app.composition.gateway.kernel_routes.live_event_stream import committed_event_stream

    reader = EventReader(database, tenant)

    async def consume() -> None:
        async for _ in committed_event_stream(reader):
            pass

    tasks = [asyncio.create_task(consume()) for _ in range(subscribers)]
    await asyncio.sleep(SETTLE_SECONDS)  # each stream's one catch-up read on connect
    settled = reader.queries
    await asyncio.sleep(seconds)
    measured = reader.queries - settled
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    reader.stop()
    return measured


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    if "test" not in url.rsplit("/", 1)[-1]:
        parser.error("use a disposable database whose name contains 'test'")
    os.environ.setdefault("OMNIX_DATABASE_URL", url)
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import ensure_local_identity
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.runtime.tenant_context import install_process_tenant

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=20))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    store = PostgresJobStoreAdapter(database=database)
    results = []
    for subscribers in (1, 10, 100):
        before = asyncio.run(_before(store, subscribers, args.seconds))
        after = asyncio.run(_after(database, tenant, subscribers, args.seconds))
        results.append({
            "subscribers": subscribers,
            "before_queries_per_second": round(before / args.seconds, 2),
            "after_queries_per_second": round(after / args.seconds, 2),
        })
        print(results[-1], flush=True)
    database.close()
    report = {"measurement": "event-delivery-idle-queries", "seconds_per_case": args.seconds,
              "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
