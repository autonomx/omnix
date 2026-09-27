"""Measure Chat recovery and queue capacity using an isolated disposable database."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace
from urllib.parse import urlparse
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def measure(url: str, samples: int) -> dict:
    from app.chat.generation_jobs import (
        ChatQueueFull,
        _ChatGenerationDispatcher,
        _ChatGenerationWork,
        recover_abandoned_chat_generation_jobs,
    )
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
    from app.persistence.repositories import PostgresIdentityRepository

    database = PostgresDatabase(DatabaseSettings(url=url))
    store = PostgresJobStoreAdapter(database)
    workspace_id = f"workspace:chat-benchmark:{uuid.uuid4().hex}"
    try:
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Chat benchmark', %s)",
                (workspace_id, store.context.user_id),
            )
            connection.execute(
                "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
                (
                    f"membership:{uuid.uuid4().hex}",
                    workspace_id,
                    store.context.user_id,
                    ["owner", "admin", "member"],
                ),
            )
            store.context = PostgresIdentityRepository(connection).load_context(
                user_id=store.context.user_id,
                workspace_id=workspace_id,
            )
            connection.execute(
                """INSERT INTO omnix_jobs (id, workspace_id, owner_user_id, module, job_type, resource_class, metadata, created_at)
                   SELECT %s || ':chat:' || n::text, %s, %s, 'chatbot', 'chat.generate', 'gpu:llm',
                          '{"compat_contract":{"compat":{"inline_execution":true}}}'::jsonb,
                          CURRENT_TIMESTAMP - INTERVAL '1 hour'
                     FROM generate_series(1, 600) AS n""",
                (workspace_id, workspace_id, store.context.user_id),
            )
            connection.execute(
                """INSERT INTO omnix_jobs (id, workspace_id, owner_user_id, module, job_type, resource_class)
                   SELECT %s || ':noise:' || n::text, %s, %s, 'image', 'image.generate', 'gpu:image'
                     FROM generate_series(1, 1000) AS n""",
                (workspace_id, workspace_id, store.context.user_id),
            )
        old_candidates = sum(
            job.type == "chat.generate" and bool(job.compat.get("inline_execution"))
            for job in store.list_jobs(limit=500)
        )
        timings = []
        for _ in range(samples):
            started = time.perf_counter()
            found = len(list(store.iter_recoverable_chat_jobs()))
            timings.append((time.perf_counter() - started) * 1000)
            assert found == 600
        started = time.perf_counter()
        recovered = recover_abandoned_chat_generation_jobs(None, store)
        recovery_ms = (time.perf_counter() - started) * 1000
        assert recovered == 600
        assert recover_abandoned_chat_generation_jobs(None, store) == 0
        with database.connection() as connection:
            event_count = connection.execute(
                "SELECT count(*) FROM omnix_job_events WHERE workspace_id = %s AND event_type = 'job.failed'",
                (workspace_id,),
            ).fetchone()[0]
            index_exists = connection.execute(
                "SELECT to_regclass('idx_omnix_jobs_chat_recovery') IS NOT NULL"
            ).fetchone()[0]
        assert event_count == 600 and index_exists

        # Hold consumers idle to measure worst-case retained scheduling work.
        # This exercises scheduling only; no providers or background hooks run.
        tracemalloc.start()
        dispatcher = _ChatGenerationDispatcher()
        dispatcher._started = True
        accepted = rejected = 0
        for index in range(10000):
            item = _ChatGenerationWork(
                chat_store=None,
                job_store=None,
                job=SimpleNamespace(
                    id=str(index), input_payload={"session_id": str(index)}
                ),
                request=None,
                context_builder=None,
                completion_hook=None,
            )
            try:
                dispatcher.submit(item)
                accepted += 1
            except ChatQueueFull:
                rejected += 1
        retained_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert accepted == dispatcher._outstanding == 128 and rejected == 9872
        timings.sort()
        return {
            "schema_version": 1,
            "mode": "isolated_postgresql_recovery_and_synthetic_idle_queue",
            "python": platform.python_version(),
            "samples": samples,
            "workload": {"abandoned_chat_jobs": 600, "newer_unrelated_jobs": 1000},
            "previous_latest_500_candidates_found": old_candidates,
            "paged_candidates_found": found,
            "scan_p50_ms": statistics.median(timings),
            "scan_p95_ms": timings[min(len(timings) - 1, int(len(timings) * 0.95))],
            "recovery_total_ms": recovery_ms,
            "recovery_jobs_per_second": recovered / (recovery_ms / 1000),
            "terminal_events": event_count,
            "repeat_recovery_count": 0,
            "recovery_index_present": index_exists,
            "idle_queue": {
                "attempted": 10000,
                "accepted": accepted,
                "rejected": rejected,
                "retained_python_bytes": retained_bytes,
                "peak_python_bytes": peak_bytes,
            },
        }
    finally:
        with database.transaction() as connection:
            connection.execute(
                "DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,)
            )
        database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--local-disposable", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("OMNIX_BENCHMARK_DATABASE_URL", "")
    if args.local_disposable:
        url = "postgresql://omnix_baseline:baseline_disposable@127.0.0.1:16432/omnix_refactor_baseline"
    if urlparse(url).path != "/omnix_refactor_baseline" or args.samples < 1:
        parser.error(
            "requires disposable omnix_refactor_baseline database and positive samples"
        )
    result = measure(url, args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
