"""RPG turn overhead without model time, at a given saved-game size (WP-5.6).

Plays turns through ``POST /api/rpg/sessions/{id}/turn`` the way the
``rpg-production-turn`` characterization does: a seeded new game, model calls
answered by its scripted fake and the narrative engine by its scripted writer,
so what is measured is the engine, the response and persistence. Before the
first turn the saved game is padded to ``--state-kb`` with a journal archive,
the kind of history a long campaign carries. Per turn it records the request
time, the time inside ``persist_foreground_turn``, the SQL statements the
process sent and the WAL bytes the database wrote.

The world-tick case (RQ-0.5) measures a catch-up of 24 in-game hours two ways,
each from the same saved game and restored before every run: the player's return
(``POST /resume`` with 24 hours elapsed: a ``world_tick`` turn, which catches up
at most ``MAX_WORLD_TICKS`` ticks), and a "wait 24 hours" turn through the turn
route. It records the time, the
statements, the ticks the resume reports, and how far each of today's clocks
moved (the environment's minutes, the campaign calendar, the simulation tick).

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/omnix_bench \\
        python -m tests.rehearsal.rpg.turn_overhead --state-kb 100 1024 --turns 200 --output turn.json

The database name must contain ``test`` or ``bench`` (or be named by
``--allow-database``), and the port must not be 5432; the database must be
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
WORLD_TICK_HOURS = 24


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


def _load(session_id: str) -> dict[str, Any]:
    from app.apps.rpg.session.service import load_session

    return load_session(session_id)


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


def _in_game_minutes(session: dict[str, Any]) -> dict[str, int]:
    """Both of today's in-game clocks: the environment's minutes and the campaign calendar's."""
    environment = (session.get("simulation_state") or {}).get("environment") or {}
    current = ((session.get("runtime_state") or {}).get("campaign_calendar") or {}).get("current") or {}
    calendar = (int(current.get("absolute_day") or 1) - 1) * 1440 + int(current.get("hour") or 0) * 60 + int(current.get("minute") or 0)
    tick = int((session.get("simulation_state") or {}).get("tick") or 0)
    return {"environment_minutes": int(environment.get("absolute_minutes") or 0), "calendar_minutes": calendar,
            "simulation_ticks": tick}


def _restore(session_id: str, snapshot: dict[str, Any]) -> None:
    """Put a saved game back as it was (an out-of-turn save on the current revision)."""
    import copy

    from app.apps.rpg.session.service import load_session, save_session

    current = load_session(session_id)
    restored = copy.deepcopy(snapshot)
    restored.setdefault("runtime_state", {})["state_revision"] = (current.get("runtime_state") or {}).get("state_revision")
    save_session(restored)


def measure_world_tick(runs: int) -> dict[str, Any]:
    """A 24-in-game-hour catch-up: the player's return (a world_tick turn), and a "wait 24 hours" turn."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from app.apps.rpg.session.turn.run import MAX_WORLD_TICKS
    from app.apps.rpg.session.new_game import RpgNewGameRequest, create_new_game_session
    from app.apps.rpg.session.service import load_session
    from tests.support.routers import include_router_registrar

    created = create_new_game_session(RpgNewGameRequest(seed=7))
    session_id = str(created["session_id"])
    app = FastAPI()
    include_router_registrar(app, register_rpg_session_routes)
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "benchmark"})
    client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": "look around"})
    snapshot = load_session(session_id)
    elapsed_seconds = WORLD_TICK_HOURS * 3600
    results: dict[str, Any] = {}
    counter = _StatementCounter()
    try:
        for case in ("resume_turn", "wait_turn"):
            elapsed_ms: list[float] = []
            statements: list[int] = []
            minutes: dict[str, list[int]] = {"environment_minutes": [], "calendar_minutes": [], "simulation_ticks": []}
            ticks: list[int] = []
            statuses: list[int] = []
            for _ in range(runs):
                _restore(session_id, snapshot)
                before = _in_game_minutes(load_session(session_id))
                counter.count = 0
                started = time.perf_counter()
                if case == "resume_turn":
                    response = client.post(f"/api/rpg/sessions/{session_id}/resume",
                                           json={"elapsed_seconds": elapsed_seconds})
                    statuses.append(response.status_code)
                else:
                    response = client.post(f"/api/rpg/sessions/{session_id}/turn",
                                           json={"command": f"wait {WORLD_TICK_HOURS} hours"})
                    statuses.append(response.status_code)
                elapsed_ms.append((time.perf_counter() - started) * 1000)
                statements.append(counter.count)
                after = _in_game_minutes(load_session(session_id))
                for clock in minutes:
                    minutes[clock].append(after[clock] - before[clock])
            results[case] = {
                "runs": runs,
                "ms": _percentiles(elapsed_ms),
                "statements": _percentiles([float(value) for value in statements]),
                "clock_advance": {clock: _percentiles([float(value) for value in values])
                                             for clock, values in minutes.items()},
                "ticks_applied": _percentiles([float(value) for value in ticks]) if ticks else None,
                "http_statuses": sorted(set(statuses)),
            }
    finally:
        counter.close()
    return {
        "requested_in_game_hours": WORLD_TICK_HOURS,
        "elapsed_seconds_given_to_resume": elapsed_seconds,
        "resume_catchup_tick_cap": MAX_WORLD_TICKS,
        "state_bytes": len(json.dumps(snapshot)),
        "cases": results,
        "budget_p95_ms": 500,
    }


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
        # The cost of a turn as the campaign grows: the same percentiles per block of 50 turns.
        "turn_request_ms_by_50_turns": [_percentiles(request_ms[start:start + 50]) for start in range(0, len(request_ms), 50)],
        "statements_by_50_turns": [_percentiles([float(value) for value in statements[start:start + 50]])
                                   for start in range(0, len(statements), 50)],
        "state_bytes_after": len(json.dumps(_load(session_id))),
        "persist_foreground_turn_ms": _percentiles(persist_ms),
        "statements_per_turn": _percentiles([float(value) for value in statements]),
        "wal_bytes_per_turn": _percentiles([float(value) for value in wal_bytes]),
        "model_calls_per_turn": round(len(model.calls) / (turns + 1), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-kb", type=int, nargs="+", default=[100, 1024])
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--world-tick-runs", type=int, default=20, help="runs of each world-tick case; 0 skips it")
    parser.add_argument("--allow-database", default="", help="a disposable database whose name lacks 'test'/'bench'")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("OMNIX_DATABASE_URL", "")
    parsed = urlparse(url)
    name = (parsed.path or "").lstrip("/")
    if (parsed.port or 5432) == 5432:
        raise SystemExit("refusing port 5432: that is the live database")
    if not (any(marker in name for marker in ("test", "bench")) or (args.allow_database and name == args.allow_database)):
        raise SystemExit("OMNIX_DATABASE_URL must name a disposable database (containing 'test' or 'bench')")
    os.environ.setdefault("OMNIX_AUTH_MODE", "disabled")
    # The per-user turn budget (RQ-8.2, on rpg-production) would refuse a benchmark's hundreds of turns.
    os.environ.setdefault("OMNIX_RPG_TURNS_PER_HOUR", "0")

    from app.jobs import store as job_store
    from app.persistence.repository_registry import register_feature_repositories
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter

    register_feature_repositories("rpg")  # as composition does: a classic new game installs the starter world
    bootstrap_postgresql_runtime()
    jobs = PostgresJobStoreAdapter()
    job_store.install_default_job_store_factory(lambda: jobs)
    results = [measure(size, args.turns) for size in args.state_kb]
    world_tick = measure_world_tick(args.world_tick_runs) if args.world_tick_runs > 0 else None
    report = {
        "schema_version": 1,
        "measurement": "RPG turn overhead without model time (WP-5.6)",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "database": name,
        "budget_p95_ms": 150,
        "budget_statements_per_turn": 20,
        "results": results,
        "world_tick": world_tick,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"results": results, "world_tick": world_tick}, indent=2))


if __name__ == "__main__":
    main()
