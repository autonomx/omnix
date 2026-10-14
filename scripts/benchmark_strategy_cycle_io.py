"""Measure the event-store reads of one trading strategy cycle (WP-7.5, the I/O half).

``benchmark_strategy_cycle.py`` measures a cycle's CPU work. Each cycle a gap
pullback configuration also reads its own event history, through
``TradingStrategyRepository.events_by_types_between``:

- the v2 qualification events since the prospective start (up to 20,000);
- the day's Stoch trend-capture entries and executions (up to 2,000);
- the day's intraday LLM events (up to 5,000).

This script seeds one strategy in a disposable database with a long history
(200,000 events over 50 days by default, of which 20,000 are qualification
events and the rest of the day's are Stoch and LLM events), then times those
three reads through the production repository. Run it on a database the list
benchmark seeded, so the table also holds other strategies' events. It refuses
a database whose name does not contain ``test`` or ``bench``.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/omnix_bench \\
        python scripts/benchmark_strategy_cycle_io.py --output docs/measurements/strategy-cycle-io.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

STRATEGY_ID = "bench-cycle-io"
NOW = datetime(2026, 10, 13, 19, 30, tzinfo=timezone.utc)
SESSION_START = datetime(2026, 10, 13, 4, 0, tzinfo=timezone.utc)  # midnight Eastern
PAYLOAD = json.dumps({"symbol": "BENCH", "notes": "x" * 900})  # about 1 KB, like a shadow execution


def _disposable(url: str) -> None:
    name = (urlparse(url).path or "").lstrip("/")
    if not any(marker in name for marker in ("test", "bench")):
        raise SystemExit(f"refusing {name!r}: the database name must contain 'test' or 'bench'")


def seed(url: str, *, history: int, qualification: int, stoch: int, llm: int) -> None:
    import psycopg

    from app.apps.trading.strategies.models import StochRsi5mConfig, StrategyRiskProfile
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import ensure_local_identity

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=1))
    try:
        context = ensure_local_identity(database)
    finally:
        database.close()
    config = StochRsi5mConfig()
    with psycopg.connect(url) as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', false)")
        connection.execute(
            """INSERT INTO omnix_trading_paper_accounts (workspace_id, account_id, name, base_currency)
               VALUES (%s, 'paper-bench-io', 'Benchmark I/O account', 'USD') ON CONFLICT DO NOTHING""",
            (context.workspace_id,),
        )
        connection.execute(
            """INSERT INTO omnix_trading_strategy_configs (workspace_id, strategy_id, account_id, owner_user_id,
                   strategy_kind, strategy_version, mode, config, risk, enabled)
               VALUES (%s, %s, 'paper-bench-io', %s, 'stoch_rsi_5m_v1', %s, 'shadow', %s::jsonb, %s::jsonb, FALSE)
               ON CONFLICT DO NOTHING""",
            (context.workspace_id, STRATEGY_ID, context.user_id, config.strategy_version,
             json.dumps(config.model_dump(mode="json")), json.dumps(StrategyRiskProfile().model_dump(mode="json"))),
        )
        if connection.execute("SELECT 1 FROM omnix_trading_strategy_events WHERE strategy_id = %s LIMIT 1",
                              (STRATEGY_ID,)).fetchone():
            return
        # Every event type in one series: the qualification, Stoch and LLM events are spread through it
        # the way a live strategy writes them, among routine evaluations.
        connection.execute(
            """INSERT INTO omnix_trading_strategy_events (workspace_id, strategy_id, event_id, instrument_id, event_type,
                   state, observed_at, idempotency_key, payload)
               SELECT %(ws)s, %(sid)s, 'tse:bench-io-' || n, 'equity:NASDAQ:B' || (n %% 200),
                      CASE
                          WHEN n <= %(stoch)s THEN (ARRAY['stoch_trend_capture_entry', 'stoch_trend_execution'])[1 + n %% 2]
                          WHEN n <= %(stoch)s + %(llm)s THEN (ARRAY['intraday_llm', 'intraday_llm_batch'])[1 + n %% 2]
                          WHEN n %% (%(history)s / %(qualification)s) = 0
                              THEN (ARRAY['shadow_execution', 'v2_shadow_replay_trade', 'v2_shadow_replay_session'])[1 + n %% 3]
                          ELSE (ARRAY['signal', 'evaluation', 'risk_decision'])[1 + n %% 3]
                      END,
                      'recorded',
                      CASE WHEN n <= %(stoch)s + %(llm)s
                           THEN %(now)s - (n * interval '1 second')
                           ELSE %(session)s - ((n - %(stoch)s - %(llm)s) * (interval '50 days' / %(history)s)) END,
                      'bench-io-' || n, %(payload)s::jsonb
                 FROM generate_series(1, %(history)s) AS n""",
            {"ws": context.workspace_id, "sid": STRATEGY_ID, "history": history, "qualification": qualification,
             "stoch": stoch, "llm": llm, "now": NOW, "session": SESSION_START, "payload": PAYLOAD},
        )
        connection.commit()
        connection.autocommit = True
        connection.execute("ANALYZE omnix_trading_strategy_events")


def measure(samples: int) -> dict:
    from app.apps.trading.strategy_repository import TradingStrategyRepository
    from app.apps.trading.strategy_v2_qualification import V2_PROSPECTIVE_START, V2_QUALIFICATION_EVENT_TYPES
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import ensure_local_identity
    from app.persistence.unit_of_work import unit_of_work

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_DATABASE_URL"], pool_min=1, pool_max=2))
    context = ensure_local_identity(database)
    repository = TradingStrategyRepository(context=context, uow_factory=lambda: unit_of_work(database))
    prospective = datetime(V2_PROSPECTIVE_START.year, V2_PROSPECTIVE_START.month, V2_PROSPECTIVE_START.day,
                           tzinfo=timezone.utc)
    reads = {
        "v2_qualification": dict(event_types=V2_QUALIFICATION_EVENT_TYPES, start_time=prospective,
                                 end_time=NOW + timedelta(seconds=1), limit=20_000),
        "stoch_trend_session": dict(event_types=("stoch_trend_capture_entry", "stoch_trend_execution"),
                                    start_time=SESSION_START, end_time=SESSION_START + timedelta(days=1), limit=2_000),
        "intraday_llm_session": dict(event_types=("intraday_llm", "intraday_llm_batch"), start_time=SESSION_START,
                                     end_time=NOW + timedelta(seconds=1), limit=5_000),
    }
    results: dict[str, dict] = {}
    cycle_ms: list[float] = []
    try:
        for _ in range(samples + 1):
            cycle = 0.0
            for name, arguments in reads.items():
                started = time.perf_counter()
                events = repository.events_by_types_between(STRATEGY_ID, **arguments)
                elapsed = (time.perf_counter() - started) * 1000
                cycle += elapsed
                results.setdefault(name, {"rows": len(events), "ms": []})["ms"].append(elapsed)
            cycle_ms.append(cycle)
    finally:
        database.close()

    def summary(values: list[float]) -> dict:
        values = sorted(values[1:])  # the first pass warms the cache
        return {"p50_ms": round(statistics.median(values), 1),
                "p95_ms": round(values[min(len(values) - 1, int(len(values) * 0.95))], 1),
                "max_ms": round(max(values), 1)}

    return {
        "reads": {name: {"rows": value["rows"], **summary(value["ms"])} for name, value in results.items()},
        "cycle_reads": summary(cycle_ms),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--history", type=int, default=200_000)
    parser.add_argument("--qualification", type=int, default=20_000)
    parser.add_argument("--stoch", type=int, default=2_000)
    parser.add_argument("--llm", type=int, default=5_000)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("OMNIX_DATABASE_URL", "")
    _disposable(url)
    seed(url, history=args.history, qualification=args.qualification, stoch=args.stoch, llm=args.llm)
    import psycopg

    with psycopg.connect(url) as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', false)")
        table_rows = connection.execute("SELECT count(*) FROM omnix_trading_strategy_events").fetchone()[0]
    result = {
        "schema_version": 1,
        "measurement": "event-store reads of one strategy cycle (WP-7.5)",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "database": (urlparse(url).path or "").lstrip("/"),
        "strategy_events_in_table": int(table_rows),
        "strategy_history": {"events": args.history, "qualification": args.qualification,
                             "stoch_today": args.stoch, "intraday_llm_today": args.llm},
        "samples": args.samples,
        **measure(args.samples),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("reads", "cycle_reads")}, indent=2))


if __name__ == "__main__":
    main()
