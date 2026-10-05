"""Seed a disposable PostgreSQL database with benchmark volumes (WP-7.6).

Writes into the local owner workspace (the one the app uses with sign-in
off), in bulk with ``generate_series``. Refuses a database whose name does not
mark it disposable (it must contain ``test`` or ``bench``). Volumes default
to the roadmap's: 100k assets, 100k jobs with events, 10k chat sessions with
1M messages, 50k agent events and 1M trading strategy events. RPG campaigns
are not seeded (RPG is being retired).

Usage:
    python scripts/seed_benchmark_data.py --database-url postgresql://omnix:omnix@127.0.0.1:55433/omnix_bench
    python scripts/seed_benchmark_data.py --database-url ... --scale 0.01   # a quick small run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PREFIX = "bench"
VOLUMES = {
    "assets": 100_000,
    "jobs": 100_000,
    "job_events_per_job": 3,
    "chat_sessions": 10_000,
    "chat_messages": 1_000_000,
    "agent_runs": 20,
    "agent_events": 50_000,
    "trading_strategies": 5,
    "trading_events": 1_000_000,
}


def _disposable(url: str) -> None:
    name = (urlparse(url).path or "").lstrip("/")
    if not any(marker in name for marker in ("test", "bench")):
        raise SystemExit(f"refusing to seed {name!r}: the database name must contain 'test' or 'bench'")


def _workspace(url: str) -> tuple[str, str]:
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import ensure_local_identity

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=1))
    try:
        context = ensure_local_identity(database)
        return context.workspace_id, context.user_id
    finally:
        database.close()


def _documents() -> tuple[str, str, str, str]:
    from app.platform.agent_runtime.contracts import AgentRunSpec, ModelRef
    from app.apps.trading.strategies.models import StochRsi5mConfig, StrategyRiskProfile

    spec = AgentRunSpec(run_id="placeholder", task="benchmark run", model=ModelRef(provider_id="test", model_id="m"))
    config = StochRsi5mConfig()
    return (
        json.dumps(spec.model_dump(mode="json")),
        json.dumps(config.model_dump(mode="json")),
        json.dumps(StrategyRiskProfile().model_dump(mode="json")),
        config.strategy_version,
    )


def seed(url: str, volumes: dict[str, int]) -> dict[str, float]:
    import psycopg

    workspace, user = _workspace(url)
    agent_spec, strategy_config, strategy_risk, strategy_version = _documents()
    timings: dict[str, float] = {}
    params = {"ws": workspace, "user": user, "prefix": PREFIX, **volumes}
    steps = (
        ("assets", """
            INSERT INTO omnix_assets (id, workspace_id, module, asset_type, mime_type, byte_size, checksum_sha256,
                                      storage_provider, storage_key, created_at, updated_at)
            SELECT 'asset:' || %(prefix)s || '-' || n, %(ws)s,
                   (ARRAY['image', 'audiobook', 'chat', 'voice'])[1 + n %% 4],
                   (ARRAY['image', 'audio', 'transcript'])[1 + n %% 3],
                   'application/octet-stream', 1024 + n, lpad(to_hex(n), 64, '0'), 'local', %(prefix)s || '/' || n,
                   now() - n * interval '1 second', now() - n * interval '1 second'
              FROM generate_series(1, %(assets)s) AS n
            ON CONFLICT DO NOTHING
        """),
        ("jobs", """
            INSERT INTO omnix_jobs (id, workspace_id, module, job_type, resource_class, status, created_at, updated_at)
            SELECT 'job:' || %(prefix)s || '-' || n, %(ws)s,
                   (ARRAY['chat', 'image', 'audiobook', 'trading'])[1 + n %% 4],
                   (ARRAY['chat.generation', 'image.generate', 'audiobook.render', 'trading.strategy.range-backtest'])[1 + n %% 4],
                   'cpu', (ARRAY['completed', 'failed', 'queued', 'canceled'])[1 + n %% 4],
                   now() - n * interval '1 second', now() - n * interval '1 second'
              FROM generate_series(1, %(jobs)s) AS n
            ON CONFLICT DO NOTHING
        """),
        ("job_events", """
            INSERT INTO omnix_job_events (workspace_id, job_id, event_type, payload, created_at)
            SELECT %(ws)s, 'job:' || %(prefix)s || '-' || n, (ARRAY['created', 'progress', 'finished'])[k], '{}'::jsonb,
                   now() - n * interval '1 second' + k * interval '1 millisecond'
              FROM generate_series(1, %(jobs)s) AS n, generate_series(1, %(job_events_per_job)s) AS k
        """),
        ("chat_sessions", """
            INSERT INTO omnix_chat_sessions (id, workspace_id, title, message_count, created_at, updated_at)
            SELECT 'chat:' || %(prefix)s || '-' || n, %(ws)s, 'Benchmark session ' || n,
                   %(chat_messages)s / %(chat_sessions)s, now() - n * interval '1 minute', now() - n * interval '1 minute'
              FROM generate_series(1, %(chat_sessions)s) AS n
            ON CONFLICT DO NOTHING
        """),
        ("chat_messages", """
            INSERT INTO omnix_chat_messages (id, workspace_id, session_id, position, role, content, created_at)
            SELECT 'msg:' || %(prefix)s || '-' || s || '-' || p, %(ws)s, 'chat:' || %(prefix)s || '-' || s, p,
                   CASE WHEN p %% 2 = 0 THEN 'user' ELSE 'assistant' END,
                   'Benchmark message ' || p || ' about topic ' || (s * 7 + p) %% 97,
                   now() - s * interval '1 minute' + p * interval '1 second'
              FROM generate_series(1, %(chat_sessions)s) AS s,
                   generate_series(0, %(chat_messages)s / %(chat_sessions)s - 1) AS p
            ON CONFLICT DO NOTHING
        """),
        ("agent_runs", """
            INSERT INTO omnix_agent_runs (workspace_id, run_id, spec, status, created_at, updated_at)
            SELECT %(ws)s, 'agent-run:' || %(prefix)s || '-' || n,
                   jsonb_set(%(agent_spec)s::jsonb, '{run_id}', to_jsonb('agent-run:' || %(prefix)s || '-' || n)),
                   'completed', now() - n * interval '1 hour', now() - n * interval '1 hour'
              FROM generate_series(1, %(agent_runs)s) AS n
            ON CONFLICT DO NOTHING
        """),
        ("agent_events", """
            INSERT INTO omnix_agent_run_events (workspace_id, run_id, sequence, event_id, event_type, payload, created_at)
            SELECT %(ws)s, 'agent-run:' || %(prefix)s || '-' || (1 + (n - 1) %% %(agent_runs)s),
                   1 + (n - 1) / %(agent_runs)s, 'event:' || %(prefix)s || '-' || n,
                   (ARRAY['model.message', 'tool.started', 'tool.completed', 'quality.stage'])[1 + n %% 4],
                   '{"source": "benchmark"}'::jsonb, now() - interval '1 day' + n * interval '1 millisecond'
              FROM generate_series(1, %(agent_events)s) AS n
            ON CONFLICT DO NOTHING
        """),
        ("trading_account", """
            INSERT INTO omnix_trading_paper_accounts (workspace_id, account_id, name, base_currency)
            VALUES (%(ws)s, 'paper-' || %(prefix)s, 'Benchmark paper account', 'USD')
            ON CONFLICT DO NOTHING
        """),
        ("trading_strategies", """
            INSERT INTO omnix_trading_strategy_configs (workspace_id, strategy_id, account_id, owner_user_id, strategy_kind,
                                                        strategy_version, mode, config, risk, enabled)
            SELECT %(ws)s, %(prefix)s || '-strategy-' || n, 'paper-' || %(prefix)s, %(user)s, 'stoch_rsi_5m_v1', %(strategy_version)s,
                   'shadow', %(strategy_config)s::jsonb, %(strategy_risk)s::jsonb, FALSE
              FROM generate_series(1, %(trading_strategies)s) AS n
            ON CONFLICT DO NOTHING
        """),
        ("trading_events", """
            INSERT INTO omnix_trading_strategy_events (workspace_id, strategy_id, event_id, instrument_id, event_type, state,
                                                       observed_at, idempotency_key, payload)
            SELECT %(ws)s, %(prefix)s || '-strategy-' || (1 + n %% %(trading_strategies)s), 'tse:' || %(prefix)s || '-' || n,
                   'equity:NASDAQ:B' || (n %% 200), (ARRAY['signal', 'evaluation', 'risk_decision'])[1 + n %% 3], 'recorded',
                   now() - n * interval '1 second', %(prefix)s || '-' || n, '{}'::jsonb
              FROM generate_series(1, %(trading_events)s) AS n
            ON CONFLICT DO NOTHING
        """),
    )
    params.update(agent_spec=agent_spec, strategy_config=strategy_config, strategy_risk=strategy_risk, strategy_version=strategy_version)
    with psycopg.connect(url, autocommit=False) as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', false), set_config('omnix.workspace_id', %s, false)", (workspace,))
        for name, sql in steps:
            started = time.perf_counter()
            connection.execute(sql, params)
            connection.commit()
            timings[name] = round(time.perf_counter() - started, 2)
            print(f"seeded {name} in {timings[name]} s", flush=True)
        connection.autocommit = True
        connection.execute("ANALYZE")
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", required=True, help="a disposable database (name contains 'test' or 'bench')")
    parser.add_argument("--scale", type=float, default=1.0, help="multiply every volume (e.g. 0.01 for a quick run)")
    args = parser.parse_args()
    _disposable(args.database_url)
    volumes = {
        key: (value if key in {"job_events_per_job", "trading_strategies"} else max(1, int(value * args.scale)))
        for key, value in VOLUMES.items()
    }
    volumes["agent_runs"] = max(1, min(volumes["agent_runs"], volumes["agent_events"]))
    volumes["chat_messages"] = max(volumes["chat_sessions"], volumes["chat_messages"])
    print(json.dumps({"volumes": volumes, "timings_seconds": seed(args.database_url, volumes)}, indent=2))


if __name__ == "__main__":
    main()
