from pathlib import Path

from app.trading.paper_analytics import lifecycle_funnel
from app.trading.strategy_repository import StrategyEvent
from datetime import datetime, timezone


def test_lifecycle_correlation_migration_uses_existing_canonical_trade_record() -> None:
    migration = Path(
        "src/app/persistence/migrations/0045_trading_trade_lifecycle_correlation.sql"
    ).read_text()
    for token in (
        "omnix_trading_paper_trade_records",
        "correlation_version",
        "strategy_revision",
        "strategy_run_id",
        "session_id",
        "setup_id",
        "trade_intent_id",
        "risk_decision_id",
        "protection_id",
        "entry_fill_ids",
        "exit_fill_ids",
        "lifecycle_state",
        "review_state",
        "trg_omnix_trading_strategy_event_correlation",
        "trg_omnix_trading_paper_trade_correlation",
    ):
        assert token in migration
    assert "CREATE TABLE" not in migration


def test_historical_strategy_revision_is_not_fabricated_during_backfill() -> None:
    migration = Path(
        "src/app/persistence/migrations/0045_trading_trade_lifecycle_correlation.sql"
    ).read_text()
    assert "the historical\n-- config revision cannot be inferred safely" in migration
    # The current config revision is read only by the BEFORE INSERT trigger for
    # future events; the bulk UPDATE intentionally does not overwrite the
    # strategy_revision column.
    bulk_backfill = migration.split("-- Existing event rows predate revision stamping.", 1)[1]
    bulk_backfill = bulk_backfill.split("ALTER TABLE omnix_trading_paper_trade_records", 1)[0]
    assert "strategy_revision =" not in bulk_backfill


def test_risk_decision_is_a_first_class_funnel_stage() -> None:
    observed = datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc)
    event = StrategyEvent(
        strategy_id="gap-v2",
        event_id="risk-1",
        run_id="run-1",
        instrument_id="equity:NASDAQ:TEST",
        event_type="risk_decision",
        state="approved",
        reason_code="RISK_ACCEPTED",
        observed_at=observed,
        idempotency_key="risk-1",
        payload={
            "session_id": "session-1",
            "setup_id": "setup-1",
            "trade_intent_id": "intent-1",
        },
    )
    funnel = {stage.stage: stage.count for stage in lifecycle_funnel([event])}
    assert funnel["RISK ELIGIBLE"] == 1
