"""Per-turn chat database time with a large session (WP-5.7).

Seeds one session with N messages (default 10,000) and 200 conversation
summaries spread over other sessions in a disposable PostgreSQL database,
then times the reads a chat turn performs:

- the session transcript load;
- the latest conversation summary of the session;
- a history search.

Usage:

    OMNIX_TEST_DATABASE_URL=... python scripts/benchmark_chat_prompt_queries.py --messages 10000 --output out.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--messages", type=int, default=10_000)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    if "test" not in url.rsplit("/", 1)[-1]:
        parser.error("use a disposable database whose name contains 'test'")
    os.environ.setdefault("OMNIX_DATABASE_URL", url)
    import psycopg

    from app.chat.persistence.chat_store import PostgresChatRepositoryAdapter
    from app.chat.persistence.chat_runtime import (
        PostgresConversationSummaryRepository,
        PostgresHistorySearchService,
    )
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import ensure_local_identity
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import install_process_tenant

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    session_id = f"chat:bench:{uuid.uuid4().hex}"
    admin_url = os.environ.get("OMNIX_TEST_ADMIN_DATABASE_URL") or url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_chat_sessions (id, workspace_id, title, profile_id, message_count) VALUES (%s, %s, 'bench', 'default', %s)",
            (session_id, tenant.workspace_id, args.messages),
        )
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO omnix_chat_messages (id, workspace_id, session_id, position, role, content) VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (f"{session_id}:{index}", tenant.workspace_id, session_id, index,
                     "user" if index % 2 == 0 else "assistant",
                     f"message {index} about topic{index % 97} with some ordinary words to search")
                    for index in range(args.messages)
                ],
            )
            cursor.executemany(
                "INSERT INTO omnix_module_records (workspace_id, module, record_type, record_id, payload) VALUES (%s, 'chat', 'conversation-summary', %s, %s::jsonb)",
                [
                    (tenant.workspace_id, f"summary:{session_id}:{index}", json.dumps({
                        "id": f"summary:{session_id}:{index}",
                        "session_id": session_id if index % 20 == 0 else f"chat:other:{index}",
                        "through_message_id": f"{session_id}:{index}", "revision": index + 1, "summary": "s",
                        "source_message_count": index + 1, "token_estimate": 1,
                        "created_at": "2026-10-01T00:00:00+00:00",
                    }))
                    for index in range(200)
                ],
            )
        admin.execute("ANALYZE omnix_chat_messages")
        admin.execute("ANALYZE omnix_module_records")
    adapter = PostgresChatRepositoryAdapter(database=database)
    summaries = PostgresConversationSummaryRepository(database)
    search = PostgresHistorySearchService(database)

    def timed(action) -> list[float]:
        samples = []
        for _ in range(args.runs):
            started = time.perf_counter()
            action()
            samples.append((time.perf_counter() - started) * 1000)
        return samples

    def load_transcript() -> None:
        with unit_of_work(database) as work:
            loaded = adapter._list_all_messages(work, session_id)
            work.rollback()
        if len(loaded) != args.messages:
            raise RuntimeError(f"loaded {len(loaded)} of {args.messages} messages")

    try:
        results = {
            "transcript_load_ms": timed(load_transcript),
            "latest_summary_ms": timed(lambda: summaries.latest(session_id)),
            "history_search_ms": timed(lambda: search.search(
                "topic42", profile_id="default", workspace_id=tenant.workspace_id, project_id=None,
            )),
        }
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_chat_messages WHERE session_id LIKE 'chat:bench:%'")
            admin.execute("DELETE FROM omnix_chat_sessions WHERE id LIKE 'chat:bench:%'")
            admin.execute("DELETE FROM omnix_module_records WHERE record_id LIKE 'summary:chat:bench:%'")
        database.close()
    report = {
        "measurement": "chat-prompt-queries",
        "messages": args.messages,
        "runs": args.runs,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "p95_ms": {name: _p95(samples) for name, samples in results.items()},
        "median_ms": {name: round(statistics.median(samples), 3) for name, samples in results.items()},
    }
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
