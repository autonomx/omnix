"""RPG turn overhead without model time, at a given saved-game size (WP-5.6).

Plays turns through ``POST /api/rpg/sessions/{id}/turn`` the way the
``rpg-production-turn`` characterization does: a seeded new game, model calls
answered by its scripted fake and the narrative engine by its scripted writer,
so what is measured is the engine, the response and persistence. Before the
first turn the saved game is padded to ``--state-kb`` with a journal archive,
the kind of history a long campaign carries. Per turn it records the request
time, the time inside ``persist_foreground_turn``, the SQL statements the
process sent and the WAL bytes the database wrote.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/omnix_bench \\
        python -m tests.rehearsal.rpg.turn_overhead --state-kb 100 1024 --turns 30 --output turn.json

The database name must contain ``test`` or ``bench``; the database must be
migrated. Sign-in is off for the measured routes.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

COMMANDS = ("look around", "talk to the bartender", "buy a drink", "go outside", "wait")


def _percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {"p50": round(statistics.median(ordered), 1), "p95": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 1),
            "max": round(max(ordered), 1)}


class _StatementCounter:
    """Counts statements sent through psycopg in this process."""

    def __init__(self) -> None:
        import psycopg

        self.count = 0
        self._originals = (psycopg.Cursor.execute, psycopg.Connection.execute)
        counter = self

        def cursor_execute(cursor, *args, **kwargs):
            counter.count += 1
            return counter._originals[0](cursor, *args, **kwargs)

        setattr(psycopg.Cursor, "execute", cursor_execute)
        # Connection.execute goes through a cursor; counting both would count twice.

    def close(self) -> None:
        import psycopg

        setattr(psycopg.Cursor, "execute", self._originals[0])


def _wal_lsn(url: str) -> int:
    import psycopg

    with psycopg.connect(url, autocommit=True) as connection:
        row = connection.execute("SELECT pg_current_wal_lsn() - '0/0'::pg_lsn").fetchone()
    return int(row[0]) if row is not None else 0


def _pad_session(session_id: str, state_kb: int) -> int:
    from app.apps.rpg.session.service import load_session, save_session

    session = load_session(session_id)
    line = "Day {day}: the road ran on past quiet farms and shuttered mills, and the rain kept on. "
    archive: list[str] = []
    size = len(json.dumps(session))
    day = 0
    while size + sum(len(entry) + 3 for entry in archive) < state_kb * 1024:
        day += 1
        archive.append(line.format(day=day) * 4)
    state = session.setdefault("state", {})
    state.setdefault("player_journal_archive", archive)
    save_session(session)
    return len(json.dumps(load_session(session_id)))


def measure(state_kb: int, turns: int) -> dict[str, Any]:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from app.apps.rpg.narration.narrative_engine import service as narrative_service
    from app.apps.rpg.narration.narrative_engine.writer import StructuredNarrativeWriter
    from app.apps.rpg.session.new_game import RpgNewGameRequest, create_new_game_session
    from app.apps.rpg.session.persistence import rpg_turn_service
    from app.providers import service as provider_service
    from tests.characterization.test_rpg_production_turn import _ScriptedModel, _scripted_narrative
    from tests.support.routers import include_router_registrar

    url = os.environ["OMNIX_DATABASE_URL"]
    model = _ScriptedModel()
    setattr(provider_service, "get_provider", lambda *args, **kwargs: model)
    setattr(narrative_service, "_production_writer",
            lambda: StructuredNarrativeWriter(_scripted_narrative, provider="scripted", model="scripted"))

    created = create_new_game_session(RpgNewGameRequest(seed=7))
    session_id = str(created["session_id"])
    state_bytes = _pad_session(session_id, state_kb)

    persist_ms: list[float] = []
    original_persist = rpg_turn_service.persist_foreground_turn

    def timed_persist(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_persist(*args, **kwargs)
        finally:
            persist_ms.append((time.perf_counter() - started) * 1000)

    setattr(rpg_turn_service, "persist_foreground_turn", timed_persist)
    app = FastAPI()
    include_router_registrar(app, register_rpg_session_routes)
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "benchmark"})
    request_ms: list[float] = []
    statements: list[int] = []
    wal_bytes: list[int] = []
    counter = _StatementCounter()
    try:
        for index in range(turns + 1):
            command = COMMANDS[index % len(COMMANDS)]
            counter.count = 0
            wal_before = _wal_lsn(url)
            started = time.perf_counter()
            response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
            elapsed = (time.perf_counter() - started) * 1000
            if response.status_code != 200:
                raise RuntimeError(f"turn {index}: HTTP {response.status_code}: {response.text[:300]}")
            if index == 0:
                persist_ms.clear()
                continue  # the first turn materializes the opening scene
            request_ms.append(elapsed)
            statements.append(counter.count - 1)  # the WAL probe's own statement
            wal_bytes.append(_wal_lsn(url) - wal_before)
    finally:
        counter.close()
        setattr(rpg_turn_service, "persist_foreground_turn", original_persist)
    return {
        "state_kb_requested": state_kb,
        "state_bytes": state_bytes,
        "turns": turns,
        "turn_request_ms": _percentiles(request_ms),
        "persist_foreground_turn_ms": _percentiles(persist_ms),
        "statements_per_turn": _percentiles([float(value) for value in statements]),
        "wal_bytes_per_turn": _percentiles([float(value) for value in wal_bytes]),
        "model_calls_per_turn": round(len(model.calls) / (turns + 1), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-kb", type=int, nargs="+", default=[100, 1024])
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("OMNIX_DATABASE_URL", "")
    name = (urlparse(url).path or "").lstrip("/")
    if not any(marker in name for marker in ("test", "bench")):
        raise SystemExit("OMNIX_DATABASE_URL must name a disposable database (containing 'test' or 'bench')")
    os.environ.setdefault("OMNIX_AUTH_MODE", "disabled")

    from app.jobs import store as job_store
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter

    bootstrap_postgresql_runtime()
    jobs = PostgresJobStoreAdapter()
    job_store.install_default_job_store_factory(lambda: jobs)
    results = [measure(size, args.turns) for size in args.state_kb]
    report = {
        "schema_version": 1,
        "measurement": "RPG turn overhead without model time (WP-5.6)",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "database": name,
        "budget_p95_ms": 150,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
