
from __future__ import annotations

from pathlib import Path

from app.trading.strategy_solana_ai_repository import (
    SOLANA_AI_STRATEGY_KIND,
    SOLANA_AI_STRATEGY_VERSION,
    SolanaAIStrategyRepository,
)


ROOT = Path(__file__).resolve().parents[2]


def test_solana_ai_has_dedicated_durable_strategy_and_decision_tables() -> None:
    migration = (
        ROOT / "app/persistence/migrations/0060_trading_solana_ai_strategy.sql"
    ).read_text(encoding="utf-8")
    repository = (
        ROOT / "app/trading/strategy_solana_ai_repository.py"
    ).read_text(encoding="utf-8")

    assert "omnix_trading_solana_ai_strategies" in migration
    assert "omnix_trading_solana_ai_decisions" in migration
    assert "REFERENCES omnix_trading_solana_ai_strategies" in migration
    assert "omnix_trading_strategy_events" not in repository
    assert SOLANA_AI_STRATEGY_KIND == "solana_ai_1m_shadow"
    assert SOLANA_AI_STRATEGY_VERSION == "solana-ai-1m-v1"
    assert SolanaAIStrategyRepository is not None
