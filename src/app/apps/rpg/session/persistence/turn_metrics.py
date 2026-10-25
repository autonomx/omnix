"""The turn route's own record of each turn, for the operations view (RQ-8.4).

One row per turn the route ran (``omnix_rpg_turn_metrics``, migration 0184): its class, whether it failed and how,
how many optional stages degraded, its time, and its model calls and model failures. A turn the game refused (a 4xx:
the campaign ended, the budget spent, a turn in progress) is no failure and is not recorded. Recording never fails a
turn. Rows past 90 days are deleted by the retention job (``declarations.py``). ``operations`` reads the rows back as days: the failure and degraded rates, latency per turn class, and the
model calls a turn makes (the provider here reports no token cost, so calls are its measure).
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)
RETENTION_DAYS = 90


def record_turn_metric(*, campaign_id: str, submission_id: str, turn_class: str, ok: bool, error: str = "",
                       degraded_stages: int = 0, complete_ms: float | None = None, model_calls: int = 0,
                       model_failures: int | Mapping[str, int] = 0) -> None:
    """Record one turn (``model_failures`` a count, or counts by kind); a failure to record is logged, never raised."""
    if isinstance(model_failures, Mapping):
        model_failures = sum(int(value or 0) for value in model_failures.values())
    from app.persistence.runtime import uses_postgresql_runtime

    if not uses_postgresql_runtime() or not campaign_id:
        return
    try:
        from app.persistence.database import default_database
        from app.persistence.unit_of_work import unit_of_work
        from app.security.tenant_context import current_tenant

        context = current_tenant()
        with unit_of_work(default_database()) as work:
            work.connection.execute(
                """
                INSERT INTO omnix_rpg_turn_metrics (workspace_id, campaign_id, submission_id, turn_class, ok, error,
                                                    degraded_stages, complete_ms, model_calls, model_failures)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (context.workspace_id, campaign_id[:300], submission_id[:300], (turn_class or "unknown")[:100], ok,
                 error[:200], max(0, int(degraded_stages)), complete_ms, max(0, int(model_calls)),
                 max(0, int(model_failures))),
            )
            work.commit()
    except Exception:
        logger.warning("rpg_turn_metric_not_recorded campaign=%s", campaign_id, exc_info=True)


def operations(days: int = 14) -> list[dict[str, Any]]:
    """The workspace's turns of the last ``days`` days, a row per day (newest first) with each turn class's latency."""
    from app.persistence.database import default_database
    from app.persistence.unit_of_work import unit_of_work
    from app.security.tenant_context import current_tenant

    context = current_tenant()
    with unit_of_work(default_database()) as work:
        rows = work.connection.execute(
            """
            SELECT (recorded_at AT TIME ZONE 'UTC')::date AS day, turn_class,
                   count(*) AS turns,
                   count(*) FILTER (WHERE NOT ok) AS failed,
                   count(*) FILTER (WHERE degraded_stages > 0) AS degraded,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY complete_ms) AS p50_ms,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY complete_ms) AS p95_ms,
                   sum(model_calls) AS model_calls,
                   sum(model_failures) AS model_failures
              FROM omnix_rpg_turn_metrics
             WHERE workspace_id = %s AND recorded_at >= CURRENT_TIMESTAMP - make_interval(days => %s)
             GROUP BY day, turn_class
             ORDER BY day DESC, turn_class
            """,
            (context.workspace_id, max(1, min(int(days), RETENTION_DAYS))),
        ).fetchall()
        work.rollback()
    by_day: dict[str, dict[str, Any]] = {}
    for day, turn_class, turns, failed, degraded, p50, p95, calls, model_failures in rows:
        entry = by_day.setdefault(str(day), {"day": str(day), "turns": 0, "failed": 0, "degraded": 0,
                                             "model_calls": 0, "model_failures": 0, "classes": []})
        entry["turns"] += int(turns)
        entry["failed"] += int(failed)
        entry["degraded"] += int(degraded)
        entry["model_calls"] += int(calls or 0)
        entry["model_failures"] += int(model_failures or 0)
        entry["classes"].append({"turn_class": str(turn_class), "turns": int(turns),
                                 "p50_ms": round(float(p50), 1) if p50 is not None else None,
                                 "p95_ms": round(float(p95), 1) if p95 is not None else None})
    days_out = []
    for entry in by_day.values():
        turns = max(1, entry["turns"])
        days_out.append({**entry, "failure_rate": round(entry["failed"] / turns, 4),
                         "degraded_rate": round(entry["degraded"] / turns, 4),
                         "model_calls_per_turn": round(entry["model_calls"] / turns, 3)})
    return days_out


__all__ = ["RETENTION_DAYS", "operations", "record_turn_metric"]
